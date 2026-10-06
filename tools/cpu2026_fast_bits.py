"""Use equivalent scalar bit scans in generated C++, preserving tool libraries."""
import json
from pathlib import Path
import re


HEADER = Path(__file__).with_suffix(".hpp")


def install(directory, prefix):
    directory = Path(directory)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", prefix):
        raise ValueError("unsupported generated C++ prefix")
    records = []
    for path in sorted(directory.glob(prefix + "*.cpp")):
        source = path.read_text()
        raw = source.count("VL_CLOG2_I(") + source.count("VL_CLOG2_Q(")
        existing = source.count("cpu26_clog2_i(") + source.count("cpu26_clog2_q(")
        if not raw and not existing:
            continue
        if raw:
            source = source.replace("VL_CLOG2_I(", "cpu26_clog2_i(")
            source = source.replace("VL_CLOG2_Q(", "cpu26_clog2_q(")
            include = '#include "cpu2026_fast_bits.hpp"\n'
            if include not in source:
                source = include + source
            path.write_text(source, newline="\n")
        records.append({"file": path.name, "calls": raw + existing})
    if records:
        target = directory / HEADER.name
        content = HEADER.read_bytes()
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)
    result = {"enabled": bool(records), "calls": sum(r["calls"] for r in records),
              "records": records, "library_files_modified": False,
              "method": "bit width of value-1; zero/one explicitly return zero"}
    (directory / (prefix + "_fast_bits.json")).write_text(
        json.dumps(result, indent=2) + "\n", newline="\n")
    return result
