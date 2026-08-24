#!/usr/bin/env python3
"""Validate architectural CommitRecord JSONL output."""

import argparse
import json
import sys


class TraceError(Exception):
    pass


REQUIRED = ("cycle", "lane", "valid", "pc", "inst", "rd", "rd_we", "value",
            "is_store", "store_addr", "store_mask", "store_data")


def load_records(path):
    records = []
    with open(path, "r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TraceError("line {} is not JSON: {}".format(line_number, exc))
            missing = [field for field in REQUIRED if field not in record]
            if missing:
                raise TraceError("line {} is missing {}".format(line_number, ",".join(missing)))
            record["_line"] = line_number
            records.append(record)
    return records


def validate(records, expected_return=None, max_cycles=None, max_no_retire=1000):
    if not records:
        raise TraceError("trace is empty")
    previous_cycle = -1
    previous_retire = 0
    lanes_by_cycle = {}
    terminal_return = None
    for record in records:
        line = record["_line"]
        cycle = int(record["cycle"])
        lane = int(record["lane"])
        if cycle < previous_cycle:
            raise TraceError("line {} moves backwards in cycle order".format(line))
        if max_cycles is not None and cycle > max_cycles:
            raise TraceError("line {} exceeds cycle watchdog".format(line))
        if lane < 0:
            raise TraceError("line {} has a negative lane".format(line))
        lanes_by_cycle.setdefault(cycle, []).append(lane)
        if record["valid"]:
            previous_retire = cycle
            if int(record["rd"]) == 0 and record["rd_we"]:
                raise TraceError("line {} writes architectural x0".format(line))
            if int(record["rd"]) == 0 and int(record["value"]) != 0 and record["rd_we"]:
                raise TraceError("line {} observes a nonzero x0 value".format(line))
            if record["is_store"] and int(record["store_mask"]) == 0:
                raise TraceError("line {} has a store with an empty mask".format(line))
            if record.get("error", False):
                raise TraceError("line {} reports an architectural error".format(line))
        elif record["rd_we"] or record["is_store"] or int(record["store_mask"]) != 0:
            raise TraceError("line {} invalid lane has side effects".format(line))
        if record.get("halted", False):
            terminal_return = int(record.get("return_value", record["value"])) & 0xFF
        if cycle - previous_retire > max_no_retire:
            raise TraceError("line {} exceeds no-retirement watchdog".format(line))
        previous_cycle = cycle
    for cycle, lanes in lanes_by_cycle.items():
        if lanes != list(range(len(lanes))):
            raise TraceError("cycle {} does not contain a contiguous lane prefix: {}".format(cycle, lanes))
    if expected_return is not None and terminal_return != (int(expected_return) & 0xFF):
        raise TraceError("return mismatch: expected {}, got {}".format(expected_return, terminal_return))
    return {"records": len(records), "last_cycle": previous_cycle, "return_value": terminal_return}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace")
    parser.add_argument("--expected-return", type=int)
    parser.add_argument("--max-cycles", type=int)
    parser.add_argument("--max-no-retire", type=int, default=1000)
    args = parser.parse_args(argv)
    summary = validate(load_records(args.trace), args.expected_return, args.max_cycles, args.max_no_retire)
    print("PASS: CommitRecord trace records={records} last_cycle={last_cycle} return={return_value}".format(**summary))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TraceError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        sys.exit(1)
