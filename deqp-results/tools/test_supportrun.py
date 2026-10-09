"""Unit tests for supportrun.py, using a fake deqp binary driven by case names."""
import os
import stat
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import supportrun  # noqa: E402

# Fake deqp: case name suffix picks behaviour (.pass/.fail/.ns/.crash/.hang/.teardowncrash).
FAKE_DEQP = textwrap.dedent("""\
    #!/usr/bin/env python3
    import os, sys, time
    path = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--deqp-caselist-file="))
    cases = [l.strip() for l in open(path) if l.strip()]
    status = {"pass": "Pass", "fail": "Fail", "ns": "NotSupported"}
    teardown_crash = False
    if any(c.endswith(".slowstart") for c in cases):
        time.sleep(3)  # slow group init before the first test
    for c in cases:
        print(f"Test case '{c}'..", flush=True)
        kind = c.rsplit(".", 1)[1]
        if kind == "crash":
            os.abort()
        if kind == "hang":
            time.sleep(60)
        if kind == "slowstart":
            kind = "ns"
        if kind == "teardowncrash":
            teardown_crash = True
            kind = "pass"
        print(f"  {status[kind]} (multi-line\\ndescription)", flush=True)
    print("DONE!")
    if teardown_crash:
        os.abort()
    sys.exit(1 if any(c.endswith(".fail") for c in cases) else 0)
    """)


class ParseOutputTest(unittest.TestCase):
    def test_multiline_description_and_pending(self):
        lines = ["Test case 'a'..", "  Fail (x", "y)", "Test case 'b'..", "  NotSupported (z)",
                 "Test case 'c'.."]
        results, pending = supportrun.parse_output(lines)
        self.assertEqual(results, {"a": "Fail", "b": "NotSupported"})
        self.assertEqual(pending, "c")

    def test_ignores_unknown_indented_words(self):
        results, pending = supportrun.parse_output(["Test case 'a'..", "  Passed (1/1)", "  Pass (ok)"])
        self.assertEqual(results, {"a": "Pass"})
        self.assertIsNone(pending)


    def test_result_after_unterminated_test_output(self):
        lines = ["Test case 'a'..", "Rendered image is not correct  Fail (bad)"]
        self.assertEqual(supportrun.parse_output(lines), ({"a": "Fail"}, None))


class HelpersTest(unittest.TestCase):
    def test_chunks(self):
        self.assertEqual(supportrun.chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_next_remaining_skips_through_culprit(self):
        self.assertEqual(supportrun.next_remaining(["a", "b", "c", "d"], {"a": "Pass", "b": "Crash"}, "b"),
                         ["c", "d"])


class RunBatchTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.deqp = os.path.join(self.dir, "fake-deqp")
        with open(self.deqp, "w") as f:
            f.write(FAKE_DEQP)
        os.chmod(self.deqp, os.stat(self.deqp).st_mode | stat.S_IEXEC)

    def run_batch(self, cases, timeout=10):
        return supportrun.run_batch(self.deqp, cases, [], timeout)

    def test_clean_run(self):
        self.assertEqual(self.run_batch(["t.pass", "t.fail", "t.ns"]),
                         {"t.pass": "Pass", "t.fail": "Fail", "t.ns": "NotSupported"})

    def test_crash_resumes_after_culprit(self):
        self.assertEqual(self.run_batch(["a.pass", "b.crash", "c.ns"]),
                         {"a.pass": "Pass", "b.crash": "Crash", "c.ns": "NotSupported"})

    def test_hang_becomes_timeout(self):
        self.assertEqual(self.run_batch(["a.pass", "b.hang", "c.pass"], timeout=2),
                         {"a.pass": "Pass", "b.hang": "Timeout", "c.pass": "Pass"})

    def test_slow_startup_is_not_a_timeout(self):
        self.assertEqual(self.run_batch(["a.slowstart", "b.ns"], timeout=1),
                         {"a.slowstart": "NotSupported", "b.ns": "NotSupported"})

    def test_teardown_crash_keeps_real_results(self):
        # The deqp-runner failure mode: all results printed, then abnormal exit.
        self.assertEqual(self.run_batch(["a.teardowncrash", "b.ns"]),
                         {"a.teardowncrash": "Pass", "b.ns": "NotSupported"})


if __name__ == "__main__":
    unittest.main()
