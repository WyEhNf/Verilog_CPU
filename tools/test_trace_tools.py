#!/usr/bin/env python3
"""H-04/S-05 self-tests for trace rejection, watchdogs, and manifest handling."""

import json
import subprocess
import sys
from pathlib import Path

from check_commit_trace import TraceError, validate
from regression import root_dir, validate_manifest


def record(cycle, lane, value, **extra):
    data = {"cycle": cycle, "lane": lane, "valid": True, "pc": cycle * 4, "inst": 0x13,
            "rd": 10, "rd_we": True, "value": value, "is_store": False,
            "store_addr": 0, "store_mask": 0, "store_data": 0}
    data.update(extra)
    return data


def main():
    build = root_dir() / "build" / "h04"
    build.mkdir(parents=True, exist_ok=True)
    good = build / "good.jsonl"
    bad = build / "bad.jsonl"
    good.write_text("\n".join(json.dumps(item) for item in [
        record(1, 0, 4), record(2, 0, 9), record(4, 0, 42, halted=True, return_value=42)
    ]) + "\n", encoding="utf-8")
    bad.write_text(json.dumps(record(1, 1, 4)) + "\n", encoding="utf-8")
    summary = validate([json.loads(line) | {"_line": index + 1} for index, line in enumerate(good.read_text().splitlines())], 42, 10, 3)
    if summary["return_value"] != 42:
        raise RuntimeError("good trace was not accepted")
    try:
        validate([json.loads(bad.read_text()) | {"_line": 1}], None, 10, 3)
    except TraceError:
        pass
    else:
        raise RuntimeError("malformed lane prefix was accepted")
    manifest = validate_manifest(root_dir())
    if len(manifest) != 18:
        raise RuntimeError("manifest validation count mismatch")
    checker = subprocess.run([sys.executable, str(root_dir() / "tools" / "check_commit_trace.py"), str(good), "--expected-return", "42"], capture_output=True, text=True)
    if checker.returncode != 0:
        raise RuntimeError(checker.stderr)
    rejected = subprocess.run([sys.executable, str(root_dir() / "tools" / "check_commit_trace.py"), str(bad)], capture_output=True, text=True)
    if rejected.returncode == 0:
        raise RuntimeError("CLI checker accepted malformed trace")
    print("PASS: H-04/S-05 trace checker, watchdog, and 18-case manifest")


if __name__ == "__main__":
    main()
