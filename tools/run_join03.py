#!/usr/bin/env python3
"""Build and execute the locally compiled JOIN-03 RV32I/RV32IM programs."""

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path


class Join03Error(Exception):
    pass


def read_manifest(path):
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for fields in csv.reader(line for line in stream
                                 if line.strip() and not line.lstrip().startswith("#")):
            if len(fields) != 6:
                raise Join03Error("manifest row must have six fields: {}".format(fields))
            rows.append({
                "name": fields[0].strip(),
                "source": fields[1].strip(),
                "arch": fields[2].strip(),
                "expected": int(fields[3]),
                "max_cycles": int(fields[4]),
                "mnemonics": [item for item in fields[5].split("|") if item],
            })
    if not rows:
        raise Join03Error("JOIN-03 manifest is empty")
    return rows


def run(command, cwd, capture=False):
    print("+ " + " ".join(str(item) for item in command), flush=True)
    completed = subprocess.run(command, cwd=str(cwd), text=True,
                               stdout=subprocess.PIPE if capture else None,
                               stderr=subprocess.STDOUT if capture else None)
    if capture and completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        raise Join03Error("command failed with status {}: {}".format(
            completed.returncode, command[0]))
    return completed.stdout or ""


def verify_mnemonics(dump_path, required):
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    missing = []
    for mnemonic in required:
        if not re.search(r"\s{}\s".format(re.escape(mnemonic)), text):
            missing.append(mnemonic)
    if missing:
        raise Join03Error("{} misses required instructions: {}".format(
            dump_path, ", ".join(missing)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="tests/join03_manifest.csv")
    parser.add_argument("--cc", required=True)
    parser.add_argument("--objdump", required=True)
    parser.add_argument("--objcopy", required=True)
    parser.add_argument("--readelf", required=True)
    parser.add_argument("--vvp")
    parser.add_argument("--simulation")
    parser.add_argument("--executable")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--report", default="build/join03/report.json")
    parser.add_argument("--config", default="unspecified")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    rows = read_manifest(root / args.manifest)
    if not args.build_only and not args.executable and not (args.vvp and args.simulation):
        raise Join03Error("execution needs --executable or --vvp plus --simulation")

    results = []
    for row in rows:
        out_dir = root / "build" / "images" / (row["name"] + "-" + row["arch"])
        build_command = [
            sys.executable, str(root / "tools" / "make_image.py"), row["source"],
            "--arch", row["arch"], "--out-dir", str(out_dir),
            "--cc", args.cc, "--objdump", args.objdump,
            "--objcopy", args.objcopy, "--readelf", args.readelf,
        ]
        run(build_command, root)
        verify_mnemonics(out_dir / (row["name"] + ".dump"), row["mnemonics"])

        result = dict(row)
        result["image"] = str((out_dir / (row["name"] + ".image")).relative_to(root))
        result["status"] = "built"
        if not args.build_only:
            plusargs = [
                "+IMAGE=" + result["image"], "+TEST=" + row["name"],
                "+EXPECTED=" + str(row["expected"]),
                "+MAX_CYCLES=" + str(row["max_cycles"]),
                "+MAX_NO_RETIRE_CYCLES=100000",
            ]
            if args.executable:
                command = [args.executable] + plusargs
            else:
                command = [args.vvp, "-N", args.simulation] + plusargs
            output = run(command, root, capture=True)
            marker = "PASS: JOIN-02 image={} return={}".format(row["name"], row["expected"])
            if marker not in output:
                raise Join03Error("{} did not produce its architectural PASS marker".format(row["name"]))
            metrics = re.search(
                r"PASS: JOIN-02 image={} return={} cycles=(\d+) instret=(\d+)".format(
                    re.escape(row["name"]), row["expected"]), output)
            if not metrics:
                raise Join03Error("{} PASS marker misses cycle/instret metrics".format(row["name"]))
            result["cycles"] = int(metrics.group(1))
            result["instret"] = int(metrics.group(2))
            result["ipc"] = round(result["instret"] / result["cycles"], 6)
            result["status"] = "passed"
        results.append(result)

    report_path = root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"format": "join03-v2", "config": args.config,
                                      "results": results},
                                      indent=2) + "\n", encoding="utf-8")
    print("PASS: JOIN-03 {} programs {}".format(
        len(results), "built" if args.build_only else "executed with expected results"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, Join03Error) as exc:
        print("FAIL: JOIN-03 {}".format(exc), file=sys.stderr)
        sys.exit(1)
