#!/usr/bin/env python3
"""Validate and run the manifest-driven architectural regression."""

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path


EXPECTED_CASES = 18


class RegressionError(Exception):
    pass


def root_dir():
    return Path(__file__).resolve().parents[1]


def read_manifest(path):
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for row in csv.reader(line for line in stream if line.strip() and not line.lstrip().startswith("#")):
            if len(row) != 4:
                raise RegressionError("manifest row must contain four fields: {}".format(row))
            rows.append({"name": row[0], "expected": int(row[1]), "max_cycles": int(row[2]), "long": bool(int(row[3]))})
    if len(rows) != EXPECTED_CASES:
        raise RegressionError("expected {} manifest cases, found {}".format(EXPECTED_CASES, len(rows)))
    if len({row["name"] for row in rows}) != EXPECTED_CASES:
        raise RegressionError("manifest contains duplicate case names")
    return rows


def validate_manifest(repo):
    rows = read_manifest(repo / "tests" / "manifest")
    data_dir = repo / "RISC-V-CPU-Simulator" / "testcases"
    missing = [row["name"] for row in rows if not (data_dir / (row["name"] + ".data")).is_file()]
    if missing:
        raise RegressionError("missing external images: {}".format(", ".join(missing)))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--runner", default=os.environ.get("CPU_RUNNER"))
    parser.add_argument("--report", default="build/regression/manifest.json")
    args = parser.parse_args(argv)
    repo = root_dir()
    rows = validate_manifest(repo)
    report_path = repo / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"format": "verilog-cpu-regression-plan-v1", "cases": rows, "status": "validated"}
    if args.validate_only:
        report["status"] = "manifest-only"
    elif not args.runner:
        raise RegressionError("CPU_RUNNER is required for execution; use --validate-only for infrastructure checks")
    else:
        results = []
        for row in rows:
            command = [args.runner, "--test", row["name"], "--max-cycles", str(row["max_cycles"])]
            completed = subprocess.run(command, cwd=str(repo), text=True, capture_output=True)
            results.append({"name": row["name"], "exit_code": completed.returncode, "stdout": completed.stdout[-4096:], "stderr": completed.stderr[-4096:]})
            if completed.returncode != 0:
                report["status"] = "failed"
                report["results"] = results
                report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                raise RegressionError("case {} failed; report saved to {}".format(row["name"], report_path))
        report["status"] = "passed"
        report["results"] = results
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: manifest {} cases, status={}, report={}".format(len(rows), report["status"], report_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RegressionError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        sys.exit(1)
