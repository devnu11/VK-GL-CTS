"""Unit tests for finalize.py."""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finalize  # noqa: E402


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


class FinalizeTest(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp()
        self.out = tempfile.mkdtemp()
        write_csv(os.path.join(self.run, "part-00.csv"),
                  [["dEQP-VK.api.a", "Pass"], ["dEQP-VK.api.b", "NotSupported"], ["dEQP-VK.api.c", "Missing"]])
        write_csv(os.path.join(self.run, "part-01.csv"),
                  [["dEQP-VK.ssbo.d", "Crash"], ["dEQP-VK.ssbo.e", "NotSupported"]])

    def read(self, name):
        return open(os.path.join(self.out, name)).read().split()

    def test_recheck_list(self):
        out = os.path.join(self.out, "recheck.txt")
        finalize.main(["recheck-list", self.run, out])
        self.assertEqual(open(out).read().split(), ["dEQP-VK.api.c", "dEQP-VK.ssbo.d"])

    def test_build_applies_recheck_and_splits(self):
        recheck = os.path.join(self.out, "recheck.csv")
        write_csv(recheck, [["dEQP-VK.api.c", "NotSupported"], ["dEQP-VK.ssbo.d", "Fail"]])
        finalize.build(self.run, self.out, recheck)
        self.assertEqual(self.read("would-run.txt"), ["dEQP-VK.api.a", "dEQP-VK.ssbo.d"])
        self.assertEqual(self.read("not-supported.txt"), ["dEQP-VK.api.b", "dEQP-VK.api.c", "dEQP-VK.ssbo.e"])

    def test_summarize(self):
        rows = finalize.summarize({"dEQP-VK.api.a": "Pass", "dEQP-VK.api.b": "NotSupported"})
        self.assertEqual(rows, [("dEQP-VK.api", 2, 1, 1)])


if __name__ == "__main__":
    unittest.main()
