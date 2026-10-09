"""Minimal parallel dEQP runner that records one status per test case.

Why not deqp-runner: it kills deqp-vk as soon as the last result line is
parsed; if the process is still tearing down, the kill turns into a bogus
"Crash" on the batch's last test and triggers reruns.  This runner waits for
deqp-vk to exit on its own, resumes after the crashing case on real crashes,
and sends the QPA log to /dev/null (results come from stdout).

Usage:
    supportrun.py --deqp PATH --caselist FILE --out results.csv
                  [--jobs 4] [--batch 2000] [--timeout 60] [-- extra deqp args]
"""
import argparse
import concurrent.futures
import csv
import os
import re
import selectors
import subprocess
import sys
import tempfile

BEGIN_RE = re.compile(r"^Test case '([^']+)'\.\.")
# Not anchored: a test may print text without a trailing newline before its result.
RESULT_RE = re.compile(r"  ([A-Za-z]+) \(")
KNOWN_STATUSES = {
    "Pass", "Fail", "NotSupported", "QualityWarning", "CompatibilityWarning",
    "InternalError", "ResourceError", "Crash", "Timeout", "Waiver", "DeviceLost",
}
CLEAN_EXIT_CODES = (0, 1)


def parse_output(lines):
    """Parse deqp stdout lines into (results dict, last test begun without a result)."""
    results = {}
    pending = None
    for line in lines:
        begin = BEGIN_RE.match(line)
        if begin:
            pending = begin.group(1)
            continue
        if pending is None:
            continue
        for result in RESULT_RE.finditer(line):
            if result.group(1) in KNOWN_STATUSES:
                results[pending] = result.group(1)
                pending = None
                break
    return results, pending


STARTUP_TIMEOUT = 120  # seconds allowed before the first "Test case" line (group init can be slow)


def read_until_idle(proc, idle_timeout, startup_timeout=STARTUP_TIMEOUT):
    """Collect proc's stdout lines; kill proc if it goes quiet for too long.

    Until the first test case starts, `startup_timeout` applies (some groups, e.g.
    video, spend seconds initialising); afterwards `idle_timeout` applies.
    Reads the raw fd (no Python buffering) so select() reflects all pending output.
    Returns (lines, timed_out)."""
    fd = proc.stdout.fileno()
    sel = selectors.DefaultSelector()
    sel.register(fd, selectors.EVENT_READ)
    data = bytearray()
    started = False
    while True:
        if not sel.select(idle_timeout if started else startup_timeout):
            proc.kill()
            return data.decode(errors="replace").splitlines(), True
        chunk = os.read(fd, 65536)
        if not chunk:
            return data.decode(errors="replace").splitlines(), False
        data += chunk
        started = started or b"Test case '" in data


def run_once(deqp, cases, extra_args, idle_timeout):
    """Run deqp once on `cases`; return (results, pending_test, exit_code_or_None).

    exit code None means the run was killed after `idle_timeout` s without output."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir="/dev/shm") as f:
        f.write("\n".join(cases) + "\n")
        caselist_path = f.name
    cmd = [deqp, f"--deqp-caselist-file={caselist_path}", "--deqp-log-filename=/dev/null"] + extra_args
    try:
        proc = subprocess.Popen(cmd, cwd=os.path.dirname(deqp), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        lines, timed_out = read_until_idle(proc, idle_timeout)
        code = proc.wait()
    finally:
        os.unlink(caselist_path)
    results, pending = parse_output(lines)
    return results, pending, None if timed_out else code


def next_remaining(cases, results, culprit):
    """Cases still to run: those after `culprit` (or the first unresolved) without a result."""
    start = cases.index(culprit) + 1 if culprit in cases else 0
    return [c for c in cases[start:] if c not in results]


def run_batch(deqp, cases, extra_args, timeout):
    """Run a batch to completion, restarting after crashes/timeouts. Returns {case: status}."""
    final = {}
    remaining = list(cases)
    while remaining:
        results, pending, code = run_once(deqp, remaining, extra_args, timeout)
        final.update(results)
        if code in CLEAN_EXIT_CODES and pending is None:
            for c in remaining:
                final.setdefault(c, "Missing")
            break
        culprit = pending or next((c for c in remaining if c not in results), None)
        if culprit is None:
            break  # every case has a result; abnormal exit happened during teardown
        final[culprit] = "Timeout" if code is None else "Crash"
        remaining = next_remaining(remaining, final, culprit)
    return final


def chunks(items, size):
    """Split `items` into consecutive lists of at most `size`."""
    return [items[i:i + size] for i in range(0, len(items), size)]


def write_results(path, cases, results):
    """Write name,status rows in caselist order."""
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        for c in cases:
            w.writerow([c, results.get(c, "Missing")])
    os.replace(tmp, path)


def main(argv):
    """Entry point: parse args, run batches in parallel, write results.csv."""
    if "--" in argv:
        split = argv.index("--")
        argv, extra = argv[:split], argv[split + 1:]
    else:
        extra = []
    ap = argparse.ArgumentParser()
    ap.add_argument("--deqp", required=True)
    ap.add_argument("--caselist", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=2000)
    ap.add_argument("--timeout", type=int, default=60, help="kill a case after this many seconds without output")
    args = ap.parse_args(argv)

    cases = [l.strip() for l in open(args.caselist) if l.strip()]
    results = {}
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = [pool.submit(run_batch, args.deqp, b, extra, args.timeout) for b in chunks(cases, args.batch)]
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            results.update(fut.result())
            print(f"batches {i}/{len(futures)} cases {len(results)}/{len(cases)}", flush=True)
    write_results(args.out, cases, results)


if __name__ == "__main__":
    main(sys.argv[1:])
