#!/usr/bin/env python3
"""Staged replica of scripts/synth.py (opt mode) for exploring mapping settings.

Same Yosys/ABC/OpenSTA commands as the course flow, split into cached stages:
  elab   : read_verilog ... proc; memory_collect            (keyed by sources)
  preabc : synth -noabc -flatten; dfflibmap; write_rtlil    (keyed by sources)
  map    : abc -constr -D; clean; hilomap; stat; write      (per ABC setting)
After mapping, flops are renamed after the RTL register they implement so STA
endpoints are readable. Official numbers must still come from `make synth`.

    python tools/staged_course_synth.py --out build/staged/d10 --period 1.0 \
        --yosys ... --abc ... --sta ... --asap7-lib ...

Tool paths default to the YOSYS, ABC, STA and ASAP7_LIB environment variables.
Outputs: summary.json, area.json, timing.json, endpoints.rpt (slack per
endpoint) and paths.rpt (full worst paths) under --out.
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

YOSYS = ABC = STA = None
LIBDIR = None


def q(v):
    return '"' + str(v).replace('\\', '\\\\').replace('"', '\\"') + '"'


def run_yosys(cwd, out, name, commands):
    script = out / f"{name}.ys"
    script.write_text("\n".join(commands) + "\n")
    subprocess.run([YOSYS, "-Q", "-T", "-q", "-l", str(out / f"{name}.log"), "-s", str(script)],
                   check=True, cwd=cwd)


def name_flops(il, named, table_path):
    """Rewrite the pre-ABC RTLIL so each flop cell carries the RTL bit it implements.

    Only cell names change. dfflibmap leaves QN -> $_NOT_ -> original Q wire.
    """
    cell = None; kind = None; qn = {}; inv = {}; conns = {}
    with il.open() as f:
        for line in f:
            s = line.strip()
            if s.startswith("cell "):
                _, kind, cell = s.split(" ", 2); conns = {}
            elif cell is not None and s.startswith("connect "):
                _, port, sig = s.split(" ", 2); conns[port] = sig
            elif cell is not None and s == "end":
                if kind.startswith("\\DFF"):
                    qn[conns.get("\\QN", "")] = cell
                elif kind == "$_NOT_":
                    inv[conns.get("\\A", "")] = conns.get("\\Y", "")
                cell = None
    used = {}; rename = {}; table = {}
    for wire, name in qn.items():
        target = inv.get(wire, "")
        if not target.startswith("\\"):
            continue
        base = "R_" + re.sub(r"[^A-Za-z0-9]+", "_", target[1:]).strip("_")
        n = used.get(base, 0); used[base] = n + 1
        new = base if n == 0 else f"{base}__{n}"
        rename[name] = new; table[new] = target[1:]
    with il.open() as f, named.open("w") as g:
        for line in f:
            s = line.strip()
            if s.startswith("cell \\DFF"):
                _, kind, cell = s.split(" ", 2)
                if cell in rename:
                    line = line.replace(cell, "\\" + rename[cell])
            g.write(line)
    table_path.write_text(json.dumps(table))
    return len(rename), len(qn)


STA_EXTRA = r'''
set_cmd_units -time ns -capacitance fF
read_verilog "@OUT@/mapped.v"
link_design student_top
set clock_port "clock"
create_clock -name core_clock -period @PERIOD@ [get_ports clock]
set_clock_transition 0.05 [get_clocks core_clock]
set_clock_uncertainty 0.05 [get_clocks core_clock]
set data_inputs {}
foreach port [all_inputs] { if {[get_full_name $port] ne "clock"} { lappend data_inputs $port } }
set_input_delay -max 0.2 -clock core_clock $data_inputs
set_input_delay -min 0.0 -clock core_clock $data_inputs
set_input_transition 0.05 $data_inputs
set_output_delay -max 0.2 -clock core_clock [all_outputs]
set_output_delay -min 0.0 -clock core_clock [all_outputs]
set_load 5.0 [all_outputs]
set_case_analysis 0 [get_ports reset]
report_checks -path_delay max -sort_by_slack -group_path_count @N@ -endpoint_path_count 1 -format end > "@OUT@/endpoints.rpt"
report_checks -path_delay max -sort_by_slack -group_path_count @M@ -endpoint_path_count 1 -format full -fields {slew capacitance fanout} -digits 4 > "@OUT@/paths.rpt"
report_tns
report_wns
exit 0
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path(__file__).resolve().parents[1],
                    help="source tree holding verilog/filelist.f and scripts/ (default: this repository)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, help="stage cache directory (default: <src>/build/staged_cache)")
    ap.add_argument("--yosys", default=os.environ.get("YOSYS"))
    ap.add_argument("--abc", default=os.environ.get("ABC"))
    ap.add_argument("--sta", default=os.environ.get("STA"))
    ap.add_argument("--asap7-lib", default=os.environ.get("ASAP7_LIB"))
    ap.add_argument("--period", type=float, default=2.0)
    ap.add_argument("--cell", default="INVx1_ASAP7_75t_R")
    ap.add_argument("--load", type=float, default=5.0)
    ap.add_argument("--sta-period", type=float, default=2.0)
    ap.add_argument("--endpoints", type=int, default=20000)
    ap.add_argument("--paths", type=int, default=60)
    ap.add_argument("--stop", choices=("elab", "preabc"))
    a = ap.parse_args()
    global YOSYS, ABC, STA, LIBDIR
    if not (a.yosys and a.abc and a.sta and a.asap7_lib):
        ap.error("set --yosys/--abc/--sta/--asap7-lib or the YOSYS/ABC/STA/ASAP7_LIB environment variables")
    YOSYS, ABC, STA, LIBDIR = a.yosys, a.abc, a.sta, Path(a.asap7_lib)
    src = a.src.resolve(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    cache = (a.cache or src / "build/staged_cache").resolve(); cache.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(src / "scripts"))
    from build import read_sources
    from fakeram import RAM_SOURCE, prepare_memories
    from synth_report import area_report
    from timing import analyze
    times = {}; t = time.time()
    sources = read_sources(src / "verilog/filelist.f")
    libs = sorted(LIBDIR.glob("*.lib")); assert len(libs) == 5
    digest = hashlib.sha256()
    for p in [*sources, RAM_SOURCE, *sorted(x for x in src.rglob("*.vh") if "build" not in x.parts)]:
        digest.update(p.name.encode()); digest.update(p.read_bytes())
    key = digest.hexdigest()
    stamp = cache / "elab.key"
    pre_ok = ((cache / "preabc.key").is_file() and (cache / "preabc.key").read_text() == key
              and (cache / "preabc_named.il").is_file())
    if not pre_ok and not (stamp.is_file() and stamp.read_text() == key and (cache / "elaborated.json").is_file()):
        (cache / "preabc.key").unlink(missing_ok=True)
        run_yosys(src, cache, "elaborate", [
            *["read_verilog -sv -D SYNTHESIS " + q(p) for p in sources if p != RAM_SOURCE],
            "read_verilog -sv -noblackbox -D SYNTHESIS " + q(RAM_SOURCE),
            "hierarchy -top student_top", "proc", "memory_collect",
            "write_json " + q(cache / "elaborated.json")])
        stamp.write_text(key)
    times["elab"] = time.time() - t; t = time.time()
    if a.stop == "elab":
        return
    seq = next(l for l in libs if "_SEQ_" in l.name)
    stamp = cache / "preabc.key"
    if not pre_ok and not (stamp.is_file() and stamp.read_text() == key and (cache / "preabc.il").is_file()):
        elaborated = json.loads((cache / "elaborated.json").read_text())
        prepared, wrappers, ram_libs, macros = prepare_memories(elaborated, cache / "ram")
        del elaborated
        (cache / "macros.json").write_text(json.dumps(macros))
        reads = ["read_liberty -lib -ignore_miss_func " + q(l) for l in [*libs, *ram_libs]]
        run_yosys(src, cache, "preabc", [
            "read_json " + q(prepared), "read_verilog " + q(wrappers), *reads,
            "hierarchy -check -top student_top",
            "synth -top student_top -noabc -flatten",
            "check -assert", "select -assert-none a:init t:$dlatch* t:$_DLATCH*",
            "dfflibmap -liberty " + q(seq),
            "write_rtlil " + q(cache / "preabc.il")])
        (cache / "prepared.json").unlink(missing_ok=True)
        stamp.write_text(key)
    times["preabc"] = time.time() - t; t = time.time()
    if a.stop == "preabc":
        return
    macros = json.loads((cache / "macros.json").read_text())
    ram_libs = sorted((cache / "ram").glob("*.lib"))
    src_il = cache / "preabc.il"; named_il = cache / "preabc_named.il"
    if not named_il.is_file() or (src_il.is_file() and named_il.stat().st_mtime < src_il.stat().st_mtime):
        counts = name_flops(src_il, named_il, cache / "flops.json")
        (cache / "flop_counts.json").write_text(json.dumps(counts))
    named, total = json.loads((cache / "flop_counts.json").read_text())
    la = " ".join("-liberty " + q(l) for l in libs)
    ala = " ".join("-liberty " + q(l) for l in [*libs, *ram_libs])
    constr = out / "abc.constr"
    constr.write_text(f"set_driving_cell {a.cell}\nset_load {a.load:.12g}\n")
    run_yosys(src, out, "map", [
        "read_rtlil " + q(cache / "preabc_named.il"),
        "abc -exe " + q(ABC) + " " + la + " -constr " + q(constr) + f" -D {a.period * 1000:.9g}",
        "clean", "delete t:$scopeinfo", "clean -purge",
        "hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L",
        "check -assert -mapped",
        f"tee -o {q(out / 'stat.json')} stat -json {ala}",
        "write_json " + q(out / "design.json"),
        "write_verilog -noattr -noexpr " + q(out / "mapped.v")])
    times["map"] = time.time() - t; t = time.time()
    area = area_report(json.loads((out / "design.json").read_text()),
                       json.loads((out / "stat.json").read_text()), macros)
    (out / "design.json").unlink()
    timing = analyze(STA, out, [*libs, *ram_libs], a.sta_period, "clock")
    (out / "timing.json").write_text(json.dumps(timing, indent=1))
    (out / "area.json").write_text(json.dumps(area, indent=1))
    tcl = "".join(f'read_liberty "{l}"\n' for l in [*libs, *ram_libs]) + \
        STA_EXTRA.replace("@OUT@", str(out)).replace("@PERIOD@", str(a.sta_period)) \
                 .replace("@N@", str(a.endpoints)).replace("@M@", str(a.paths))
    (out / "extra.tcl").write_text(tcl)
    with (out / "extra.log").open("w") as f:
        subprocess.run([STA, "-no_init", "-exit", "extra.tcl"], cwd=out, stdout=f, stderr=subprocess.STDOUT)
    times["sta"] = time.time() - t
    flat = {k: v for k, v in area.items() if isinstance(v, (int, float))}
    summary = {"area": flat, "fmax": timing["estimated_fmax_mhz"], "tmin": timing["minimum_period_ns"],
               "slack": timing["worst_setup_slack_ns"], "period": a.period, "cell": a.cell, "load": a.load,
               "flops_named": [named, total], "sec": {k: round(v) for k, v in times.items()}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
