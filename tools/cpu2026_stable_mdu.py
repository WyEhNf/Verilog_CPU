"""Install a conservative settled-core cache in recognized Verilator output.

This is host scheduling only. It neither changes RTL nor collapses CPU clocks.
Unknown generated layouts retain the original evaluator.
"""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from cpu2026_generated_names import load_names


TEMPLATE = Path(__file__).with_name("cpu2026_stable_mdu.hpp.in")
MDU_PATH = ("student_top__DOT__core__DOT__g_ooo_backend__DOT__backend"
            "__DOT__mdu__DOT__gen_unified_mdu__DOT__unified")


def fixed_state_fields(header):
    """Require fixed embedded data, including generated unpacked arrays."""
    section = header.split("// DESIGN SPECIFIC STATE", 1)[1].split(
        "// INTERNAL VARIABLES", 1)[0]
    section = re.sub(r"//[^\n]*|/\*.*?\*/", "", section, flags=re.S)
    fields = []
    for line in section.splitlines():
        line = line.strip()
        if not line or line in ("struct {", "};"):
            continue
        port = re.fullmatch(r"VL_(?:IN|OUT|INOUT)(?:8|16|64|W)?"
                            r"\(\s*(\w+)\s*,[^;]+\);", line)
        if port:
            fields.append(port[1])
            continue
        member = re.fullmatch(r"(.+)\s+(\w+);", line)
        if (not member or not re.fullmatch(
                r"(?:Vl(?:Wide|Unpacked|TriggerVec)|[CISQ]Data|\d+|[\s,<>])+",
                member[1])):
            raise ValueError("unsupported MDU state declaration: " + line)
        fields.append(member[2])
    if not fields or len(fields) != len(set(fields)):
        raise ValueError("unrecognized MDU fixed state")
    return fields


def install(directory, prefix):
    directory = Path(directory)
    report = {"enabled": False}
    try:
        mapping = load_names(directory, prefix)
        root = prefix + "_" + mapping["__024root"]
        syms = prefix + "_" + mapping["_Syms"]
        types = [value for key, value in mapping.items()
                 if key.startswith("rv32m_mdu_iterative__")]
        if len(types) != 1:
            raise ValueError("expected one iterative MDU type")
        mdu = prefix + "_" + types[0]
        cell = mapping["TOP__" + MDU_PATH]
        symbols = (directory / (syms + ".h")).read_text()
        instances = re.findall(r"^\s*(" + re.escape(prefix) +
                               r"_\w+)\s+(\w+);", symbols, re.M)
        if instances != [(root, "TOP"), (mdu, cell)]:
            raise ValueError("cache requires all remaining state in the root object")
        source = (directory / (prefix + ".cpp")).read_text()
        root_header = (directory / (root + ".h")).read_text()
        mdu_header = (directory / (mdu + ".h")).read_text()
        mdu_fields = fixed_state_fields(mdu_header)
        if mdu_fields[0] != mapping["clk_i"]:
            raise ValueError("unrecognized first MDU state member")
        # The current design has no clock-sensitive combinational logic.
        # Generated trigger state and all functional state remain in the snapshot.
        root_text = "\n".join(p.read_text() for p in
                               directory.glob(root + "__DepSet*.cpp")
                               if not p.name.endswith("__Slow.cpp"))
        # 5.040 expresses the same object accesses through this reference.
        # Normalize only for structural checks; leave generated code intact.
        if "vlSelfRef." in root_text:
            if "auto& vlSelfRef = std::ref(*vlSelf).get();" not in root_text:
                raise ValueError("unrecognized generated self reference")
            root_text = root_text.replace("vlSelfRef.", "vlSelf->")
        crossings = set(re.findall(r"vlSymsp->" + re.escape(cell) +
                                   r"\.(\w+)", root_text))
        expected = {mapping[name] for name in (
            "__PVT__out_valid", "__Vcellout__output_owner__data_o",
            "req_ready_o", "resp_valid_o",
            "__Vcellinp__operation_cancel_guard__active_i")}
        if crossings != expected:
            raise ValueError("unrecognized MDU to root boundary")
        mdu_text = "\n".join(p.read_text() for p in
                              directory.glob(mdu + "__DepSet*.cpp")
                              if not p.name.endswith("__Slow.cpp"))
        definitions = re.findall(r"^(?:VL_INLINE_OPT )?void (" +
                                 re.escape(mdu) + r"__\w+)\(", mdu_text, re.M)
        # 5.020 emits four NBA regions; 5.040 without scoped DFG emits
        # three (two with native combinational adders). Require the complete
        # known set, preserve call order, and check crossing after each region.
        nba_count = len(definitions) - 1
        if nba_count not in (2, 3, 4):
            raise ValueError("unrecognized MDU evaluation region count")
        functions = [mdu + "__" + mapping[region + "__TOP__" + MDU_PATH +
                     "__" + str(index)] for region, index in
                     [("_ico_sequent", 0)] + [("_nba_sequent", i) for i in range(nba_count)]]
        if set(definitions) != set(functions) or len(definitions) != len(functions):
            raise ValueError("unrecognized MDU evaluation regions")
        calls = re.findall(r"(" + re.escape(mdu) + r"__\w+)\(\(&vlSymsp->" +
                           re.escape(cell) + r"\)\);", root_text)
        if sorted(calls) != sorted(functions):
            raise ValueError("expected one call to each original MDU region")
        nba_calls = [f for f in calls if f != functions[0]]
        if nba_calls != functions[1:]:
            raise ValueError("unrecognized original MDU transition order")
        debugless = re.sub(r"#ifdef VL_DEBUG\n.*?#endif[^\n]*\n", "",
                           root_text, flags=re.S)
        if len(re.findall(r"vlSelf->clock\b", debugless)) != 2:
            raise ValueError("clock must only feed the generated edge trigger")
        if re.search(r"vlSymsp->TOP\.\w+(?:\[[^\]]+\])?\s*(?:=(?!=)|\+=|-=)", mdu_text):
            raise ValueError("MDU must not write root state")
        fields = set(re.findall(r"vlSymsp->TOP\.(\w+)", mdu_text))
        if len(fields) != 5 or "reset" not in fields:
            raise ValueError("unrecognized root to MDU boundary")
        # Ignored counter fields must be observable bookkeeping only: one
        # increment, one staging copy, one final write, with no other reader.
        counters = ["debug_core_cycles"] + ["student_top__DOT__core__DOT__" + c
                    for c in ("perf_frontend_empty_cycles", "perf_backend_stall_cycles",
                              "perf_no_commit_cycles", "perf_commit_active_cycles",
                              "perf_issue_count", "perf_rob_full_cycles",
                              "perf_rs_full_cycles", "perf_lsq_full_cycles",
                              "perf_branch_pending_cycles", "perf_mdu_busy_cycles")]
        for name in counters:
            actual = name if name == "debug_core_cycles" else mapping[name]
            delayed = mapping["__Vdly__" + name]
            if (len(re.findall(r"vlSelf->" + re.escape(actual) + r"\b", root_text)) != 3
                    or not re.search(r"vlSelf->" + re.escape(actual) +
                                     r"\s*=\s*vlSelf->" + re.escape(delayed) + r";", root_text)
                    or not re.search(r"vlSelf->" + re.escape(delayed) +
                                     r"\s*=\s*vlSelf->" + re.escape(actual) + r";", root_text)):
                raise ValueError("counter has an unrecognized reader: " + name)
        values = {"ROOT_CLASS": root, "MDU_CLASS": mdu,
                  "MDU_LAST_FIELD": mdu_fields[-1],
                  "ROOT_EVAL": root + "__" + mapping["_eval"],
                  "MDU_DECLARATIONS": "\n".join("void " + f + "(Mdu*);" for f in functions),
                  "MDU_NBA_CALLS": "\n".join(
                      "  if(good){" + f + "(&m);good=same_cross();}" for f in functions[1:])}
        values.update({"MDU_FUNC_" + str(i): f for i, f in enumerate(functions)})

        def replace(match):
            key = match[1]
            if key.startswith("ID:"):
                identifier = mapping[key[3:]]
                if not re.search(r"\b" + re.escape(identifier) + r"\b",
                                 root_header + mdu_header):
                    raise ValueError("required field missing: " + key[3:])
                return identifier
            return values[key]

        header = re.sub(r"@([^@]+)@", replace, TEMPLATE.read_text())
        original = "    " + values["ROOT_EVAL"] + "(&(vlSymsp->TOP));"
        if source.count(original) != 1:
            raise ValueError("unrecognized top evaluator call")
        replacement = (
            "    auto& root = vlSymsp->TOP;\n"
            "    auto& unit = vlSymsp->" + cell + ";\n"
            "    const bool rising = root.clock && !root."
            + mapping["__Vtrigprevexpr___TOP__clock__0"] + ";\n"
            "    if (!cpu2026_stable_mdu::try_eval(root, unit, contextp()->calcUnusedSigs())) {\n"
            "        " + values["ROOT_EVAL"] + "(&root);\n"
            "        cpu2026_stable_mdu::observe(root, unit, rising);\n"
            "    }")
        # A fresh model never inherits cached state from a destroyed model.
        init = "        vlSymsp->__Vm_didInit = true;"
        if source.count(init) != 1:
            raise ValueError("unrecognized initialization")
        source = source.replace(init, init + "\n        cpu2026_stable_mdu::reset("
                                "vlSymsp->TOP, vlSymsp->" + cell + ");")
        source = source.replace(original, replacement)
        source = source.replace('#include "' + prefix + '__pch.h"',
                                '#include "' + prefix + '__pch.h"\n'
                                '#include "cpu2026_stable_mdu.hpp"', 1)
        (directory / "cpu2026_stable_mdu.hpp").write_text(header, newline="\n")
        (directory / (prefix + ".cpp")).write_text(source, newline="\n")
        report = {"enabled": True, "root_class": root, "mdu_class": mdu,
                  "mdu_to_root_fields": sorted(crossings),
                  "root_to_mdu_fields": sorted(fields),
                  "mdu_snapshot_first": mdu_fields[0],
                  "mdu_snapshot_last": mdu_fields[-1],
                  "mdu_fixed_fields": len(mdu_fields),
                  "mdu_regions": functions,
                  "stats_preserved": 10, "cpu_cycles_collapsed": False}
    except (OSError, KeyError, IndexError, ValueError, ET.ParseError) as error:
        report["reason"] = str(error)
    (directory / (prefix + "_stable_mdu.json")).write_text(
        json.dumps(report, indent=2) + "\n", newline="\n")
    return report
