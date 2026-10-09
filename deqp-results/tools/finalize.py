"""Merge chunk results, apply recheck results, and write the would-run / not-supported lists.

Usage:
    finalize.py recheck-list <run_dir> <out_caselist>   # cases worth re-running
    finalize.py build <run_dir> <out_dir> [recheck.csv]  # merge + write lists and summary

"Not supported" = NotSupported status.  Everything else (Pass, Fail, Crash, ...) passed
the support checks and would execute on the profiled device.
"""
import collections
import csv
import glob
import os
import sys

RECHECK_STATUSES = {"Crash", "Missing", "Timeout", "InternalError"}
NOT_SUPPORTED = "NotSupported"


def load_results(run_dir):
    """Ordered {case: status} from all part-*.csv files in chunk order."""
    results = {}
    for path in sorted(glob.glob(os.path.join(run_dir, "part-*.csv"))):
        with open(path, newline="") as f:
            for name, status in csv.reader(f):
                results[name] = status
    return results


def load_csv(path):
    """{case: status} from one results CSV."""
    with open(path, newline="") as f:
        return dict(csv.reader(f))


def write_lines(path, lines):
    """Write one item per line."""
    with open(path, "w") as f:
        f.writelines(l + "\n" for l in lines)


def group_of(case, depth=2):
    """Top-level group of a case name, e.g. dEQP-VK.api."""
    return ".".join(case.split(".")[:depth])


def summarize(results):
    """Rows of (group, total, would_run, not_supported) sorted by group."""
    totals = collections.defaultdict(lambda: [0, 0])
    for case, status in results.items():
        row = totals[group_of(case)]
        row[0] += 1
        row[1] += status == NOT_SUPPORTED
    return [(g, t, t - ns, ns) for g, (t, ns) in sorted(totals.items())]


def build(run_dir, out_dir, recheck_path=None):
    """Merge and write would-run.txt, not-supported.txt, results.csv, summary.csv."""
    results = load_results(run_dir)
    if recheck_path:
        results.update(load_csv(recheck_path))
    os.makedirs(out_dir, exist_ok=True)
    write_lines(os.path.join(out_dir, "would-run.txt"), [c for c, s in results.items() if s != NOT_SUPPORTED])
    write_lines(os.path.join(out_dir, "not-supported.txt"), [c for c, s in results.items() if s == NOT_SUPPORTED])
    with open(os.path.join(out_dir, "results.csv"), "w", newline="") as f:
        csv.writer(f).writerows(results.items())
    with open(os.path.join(out_dir, "summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "total", "would_run", "not_supported"])
        w.writerows(summarize(results))
    counts = collections.Counter(results.values())
    ns = counts.get(NOT_SUPPORTED, 0)
    print(f"total {len(results):,}  would-run {len(results) - ns:,}  not-supported {ns:,}")
    print("statuses:", dict(sorted(counts.items())))


def main(argv):
    if argv[0] == "recheck-list":
        results = load_results(argv[1])
        write_lines(argv[2], [c for c, s in results.items() if s in RECHECK_STATUSES])
    elif argv[0] == "build":
        build(*argv[1:])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
