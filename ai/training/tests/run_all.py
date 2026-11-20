"""Run every NIRVA pipeline test suite and guard data/ against changes.

Records a SHA-256 checksum of every file under data/ (recursively, including
data/archive/) before the suites run, runs each suite, then checksums again.
Any changed, added or removed file under data/ fails the run, even if every
suite passed.

Usage (from the project root):
    ai/.venv/Scripts/python.exe ai/training/tests/run_all.py

Exit status: 0 when every suite passes and data/ is unchanged, 1 otherwise.
"""

import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[2]
DATA = ROOT / "data"

sys.dont_write_bytecode = True
sys.path.insert(0, str(TESTS))
from test_golden import diff_checksums, tree_checksums  # noqa: E402

SUITES = ("test_pipeline.py", "test_golden.py", "test_quality_checks.py")


def main():
    before = tree_checksums(DATA)
    print(f"data/ checksums recorded: {len(before)} files\n")

    failed = []
    for suite in SUITES:
        print(f"######## {suite} ########", flush=True)
        code = subprocess.run([sys.executable, "-B", str(TESTS / suite)]).returncode
        if code != 0:
            failed.append(suite)
        print()

    after = tree_checksums(DATA)
    changed, added, removed = diff_checksums(before, after)

    print("######## data/ integrity ########")
    print(f"Files before: {len(before)}  after: {len(after)}")
    for label, paths in (("CHANGED", changed), ("ADDED", added), ("REMOVED", removed)):
        for path in paths:
            print(f"{label}: data/{path}")
    data_ok = not (changed or added or removed)
    print("data/ unchanged" if data_ok else "data/ WAS MODIFIED BY THE TEST RUN")

    print("\n######## Summary ########")
    for suite in SUITES:
        print(f"{'FAIL' if suite in failed else 'PASS'} {suite}")
    print(f"{'PASS' if data_ok else 'FAIL'} data/ integrity")
    return 0 if not failed and data_ok else 1


if __name__ == "__main__":
    sys.exit(main())
