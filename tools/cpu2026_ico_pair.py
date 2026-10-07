#!/usr/bin/env python3
"""Reuse settled input-combinational logic while external inputs stay unchanged."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from cpu2026_generated_names import load_names

TEMPLATE = Path(__file__).with_suffix(".hpp.in")
INPUTS = {"clock", "reset", "rdata", "arready", "rresp", "rvalid",
          "awready", "wready", "bresp", "bvalid"}


def install(directory, prefix):
    directory = Path(directory)
    report = {"enabled": False}
    try:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", prefix):
            raise ValueError("unsupported C++ prefix")
        boundary = json.loads((directory / (prefix + "_stable_mdu.json")).read_text())
        if not boundary["enabled"]:
            raise ValueError("requires the recognized two-object MDU schedule")
        mapping = load_names(directory, prefix)
        top_header = (directory / (prefix + ".h")).read_text()
        ports = re.findall(r"VL_IN(8|16|64|W)?\(&([A-Za-z_][A-Za-z0-9_]*),(\d+),(\d+)\);",
                           top_header)
        inputs = {port[1] for port in ports}
        widths = {name: (kind, int(high), int(low)) for kind, name, high, low in ports}
        expected_widths = {name: ("8", 0, 0) for name in INPUTS - {"rdata", "rresp", "bresp"}}
        expected_widths.update({"rdata": ("", 31, 0), "rresp": ("8", 1, 0), "bresp": ("8", 1, 0)})
        if inputs != INPUTS or widths != expected_widths:
            raise ValueError("unrecognized top input ports")
        root = boundary["root_class"]
        root_eval = root + "__" + mapping["_eval"]
        ico = root + "__" + mapping["_eval_ico"]
        hot_source = "\n".join(path.read_text() for path in
                               directory.glob(root + "__DepSet*.cpp")
                               if not path.name.endswith("__Slow.cpp"))
        hot_source = re.sub(r"#ifdef VL_DEBUG\n.*?#endif[^\n]*\n", "", hot_source, flags=re.S)
        if "vlSelfRef." in hot_source:
            if "auto& vlSelfRef = std::ref(*vlSelf).get();" not in hot_source:
                raise ValueError("unrecognized generated self reference")
            hot_source = hot_source.replace("vlSelfRef.", "vlSelf->")
        edge = (",((IData)(vlSelf->clock)&(~(IData)(vlSelf->"
                + mapping["__Vtrigprevexpr___TOP__clock__0"] + "))));")
        edges = re.findall(re.escape("vlSelf->" + mapping["__VactTriggered"])
                           + r"\.(?:set|setBit)\(([0-9]+)U" + re.escape(edge),
                           re.sub(r"\s+", "", hot_source))
        if len(edges) != 1:
            raise ValueError("unrecognized rising clock trigger")
        # Check only callees of the skipped region. The original NBA/active
        # assertion code still executes, including its diagnostic timestamps.
        definitions = {}
        for kind in (root, boundary["mdu_class"]):
            for path in directory.glob(kind + "__DepSet*.cpp"):
                if path.name.endswith("__Slow.cpp"):
                    continue
                text = path.read_text()
                pattern = r"^(?:VL_INLINE_OPT )?void (" + re.escape(kind) + r"__\w+)\([^)]*\) \{"
                for definition in re.finditer(pattern, text, re.M):
                    end = text.find("\n}\n", definition.end())
                    if end < 0 or definition[1] in definitions:
                        raise ValueError("unrecognized input-region function layout")
                    definitions[definition[1]] = text[definition.end():end]
        pending, visited = [ico], set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            body = definitions[name]
            visited.add(name)
            if re.search(r"\bVL_(?:TIME|RANDOM|URANDOM)\w*\s*\(", body):
                raise ValueError("input region has a time/random dependency")
            pending.extend(re.findall(r"\b(" + re.escape(root) + r"__\w+|"
                                      + re.escape(boundary["mdu_class"]) + r"__\w+)\(", body))
        marker = "cpu2026_ico_pair::"
        top_path = directory / (prefix + ".cpp")
        top = top_path.read_text()
        if marker in top:
            raise ValueError("input region already patched; regenerate before installing")
        matches = []
        for path in directory.glob(root + "__DepSet*.cpp"):
            text = path.read_text()
            definition = re.search(r"\bvoid " + re.escape(ico) + r"\([^)]*\) \{", text)
            if definition:
                matches.append((path, text, definition.end()))
        if len(matches) != 1:
            raise ValueError("unrecognized input-combinational entry")
        ico_path, ico_source, insert = matches[0]
        activity = mapping["__Vm_traceActivity"]
        activity_write = "vlSelf->" + activity + "[1U] = 1U;"
        if ico_source.replace("vlSelfRef.", "vlSelf->").count(activity_write) != 1:
            raise ValueError("unrecognized input-region waveform activity")
        original = "        " + root_eval + "(&root);"
        if top.count(original) != 1:
            raise ValueError("unrecognized full evaluator call")
        after = "        cpu2026_stable_mdu::observe(root, unit, rising);\n    }"
        if top.count(after) != 1:
            raise ValueError("unrecognized stable scheduling boundary")
        initialization = re.search(r"        cpu2026_stable_mdu::reset\(([^;]+)\);", top)
        if not initialization:
            raise ValueError("unrecognized model initialization")
        values = {
            "ROOT_CLASS": root, "MDU_CLASS": boundary["mdu_class"],
            "ROOT_EVAL": root_eval,
            "MDU_FIRST_FIELD": boundary["mdu_snapshot_first"],
            "MDU_LAST_FIELD": boundary["mdu_snapshot_last"],
            "NBA_FIELD": mapping["__VnbaTriggered"],
            "PREVIOUS_CLOCK": mapping["__Vtrigprevexpr___TOP__clock__0"],
        }
        header = re.sub(r"@([^@]+)@", lambda m: values[m[1]], TEMPLATE.read_text())
        top = top.replace(initialization[0],
                          "        cpu2026_ico_pair::reset(" + initialization[1] + ");\n"
                          + initialization[0], 1)
        top = top.replace(original,
                          "        cpu2026_ico_pair::eval(root, unit, contextp()->calcUnusedSigs());")
        top = top.replace(after, after + " else {\n"
                          "        cpu2026_ico_pair::reset(root, unit);\n    }")
        include = '#include "cpu2026_ico_pair.hpp"\n'
        top = include + top
        ico_source = (include + ico_source[:insert] + "\n"
                      "    if (cpu2026_ico_pair::skip) { " + activity_write
                      + " return; }\n" + ico_source[insert:])
        (directory / "cpu2026_ico_pair.hpp").write_text(header, newline="\n")
        ico_path.write_text(ico_source, newline="\n")
        top_path.write_text(top, newline="\n")
        report = {"enabled": True, "root_class": root,
                  "mdu_class": boundary["mdu_class"],
                  "ico_entry": ico, "ico_file": ico_path.name,
                  "input_ports": sorted(inputs),
                  "clock_trigger_index": int(edges[0]),
                  "input_region_functions_checked": len(visited),
                  "reuse_after": "completed full evaluation with identical inputs",
                  "register_edges_skipped": False,
                  "mdusize_guard_bytes": 1024}
    except (OSError, KeyError, ValueError, ET.ParseError) as error:
        report["reason"] = str(error)
    (directory / (prefix + "_ico_pair.json")).write_text(
        json.dumps(report, indent=2) + "\n", newline="\n")
    return report
