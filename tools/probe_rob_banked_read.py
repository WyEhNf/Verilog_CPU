"""Price/time the complete actual standalone ROB, never a CPU result.

Use every original ROB port and field, original default ABC and five ASAP7
libraries, plus independent raw Decimal pricing. Only the combinational read
layout differs. No SRAM or port is fabricated, removed or made zero area.
"""
import argparse
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from run_course_sram_area import ROOT, FRAMEWORK, digest, load_course, quote
from verify_course_axi_area import expand_stat_census


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    candidate, out = args.candidate_root.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh standalone ROB probe directory')
    libs = sorted((ROOT/'.deps/course_asap7_r28/lib').glob('*.lib'))
    if len(libs) != 5 or sum('_SEQ_' in lib.name for lib in libs) != 1:
        raise SystemExit('Exactly five original course libraries required')
    names = [Path(name) for name in (
        'rtl/backend/rv32_rob.v', 'rtl/common/rv32_control_register_bank.v',
        'rtl/common/rv32_asap7_fanout.v', 'rtl/rv32im_defs.vh',
        'tools/probe_rob_banked_read.py', 'tools/run_course_sram_area.py',
        'tools/run_course_full_timing.py', 'tools/verify_course_axi_area.py',
        '.deps/RISC-V-CPU-2026/scripts/synth_report.py',
        '.deps/RISC-V-CPU-2026/scripts/timing.py', '.deps/RISC-V-CPU-2026/scripts/timing.tcl')]
    names += [lib.relative_to(ROOT) for lib in libs]
    snapshot, frozen, origins = out/'source_snapshot', {}, {}
    for name in names:
        source = candidate/name if (candidate/name).is_file() else ROOT/name
        target = snapshot/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source,target)
        frozen[name.as_posix()] = digest(target)
        origins[name.as_posix()] = dict(path=str(source),sha256=digest(source))
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite/'bin/yosys.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    raw_libs = [snapshot/lib.relative_to(ROOT) for lib in libs]
    reads = ['read_liberty -lib -ignore_miss_func '+quote(lib) for lib in raw_libs]
    libargs = ' '.join('-liberty '+quote(lib) for lib in raw_libs)
    reporter = load_course('synth_report')
    results = []

    def check():
        for name,expected in frozen.items():
            if digest(snapshot/name) != expected:
                raise SystemExit('Frozen ROB probe input changed: '+name)
        for row in origins.values():
            if digest(Path(row['path'])) != row['sha256']:
                raise SystemExit('ROB probe source changed: '+row['path'])

    for mode in (0,1):
        case = out/f'bank{mode}'
        case.mkdir()
        parameters = dict(BE_WIDTH=4,ROB_ENTRIES=64,PHYS_REGS=64,PHYS_ADDR_WIDTH=6,
                          GENERATION_WIDTH=8,CHECKPOINT_WIDTH=192,CHECKPOINT_IMPL=1,
                          STORE_BUFFERED_RETIRE=1,ROB_CONTROL_REGISTER_BANKS=0,
                          ASAP7_FANOUT_BUFFERS=0,COMMIT_BANKED_READ=mode)
        script, log = case/'map.ys', case/'map.log'
        commands = [
            'read_verilog -sv -D SYNTHESIS -I rtl '+
                ' '.join(quote(snapshot/name) for name in names[:3]),
            'chparam '+' '.join(f'-set {key} {value}' for key,value in parameters.items())+' rv32_rob',
            'rename rv32_rob student_top', *reads, 'hierarchy -check -top student_top',
            'synth -top student_top -noabc -flatten', 'check -assert',
            'select -assert-none a:init t:$dlatch* t:$_DLATCH*',
            'dfflibmap -liberty '+quote(next(lib for lib in raw_libs if '_SEQ_' in lib.name)),
            'write_rtlil '+quote(case/'prepared.il'), 'abc '+libargs+' -D 2000', 'clean',
            'delete t:$scopeinfo','clean -purge',
            'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
            'check -assert -mapped','tee -o '+quote(case/'stat.json')+' stat -json '+libargs,
            'write_json '+quote(case/'design.json'),
            'write_verilog -noattr -noexpr '+quote(case/'mapped.v'),
            'design -reset',*reads,'read_verilog '+quote(case/'mapped.v'),
            'hierarchy -check -top student_top','check -assert -mapped']
        check()
        script.write_text('\n'.join(commands)+'\n')
        print(f'START standalone actual ROB bank{mode} default ABC; NOT CPU',flush=True)
        with log.open('w') as stream:
            subprocess.run([str(yosys),'-T','-s',str(script)],cwd=snapshot,env=env,
                           stdout=stream,stderr=subprocess.STDOUT,check=True)
        check()
        design = json.loads((case/'design.json').read_text())
        statistics = json.loads((case/'stat.json').read_text())
        area = reporter.area_report(design,statistics,{})
        leaves, hierarchy = expand_stat_census(statistics)
        if hierarchy or leaves != Counter(cell['type'] for cell in design['modules']['student_top']['cells'].values()):
            raise SystemExit('Actual standalone ROB flat physical census mismatch')
        prices = {}
        for lib in raw_libs:
            for kind,body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',lib.read_text(),re.S):
                match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)',body,re.M)
                if not match:
                    raise SystemExit('Missing original raw ROB leaf price: '+kind)
                price = Decimal(match[1])
                if kind in prices and prices[kind] != price:
                    raise SystemExit('Conflicting original ROB leaf price: '+kind)
                prices[kind] = price
        if set(leaves)-set(prices) or area['sram_instances']:
            raise SystemExit('Unpriced ROB leaf or unexpected memory')
        total = sum((prices[kind]*count for kind,count in leaves.items()),Decimal(0))
        if abs(total-Decimal(str(area['area_um2']))) >= Decimal('0.00001'):
            raise SystemExit('Original course and independent ROB price mismatch')
        audit = dict(status='COMPLETE',area=area,independent_area_um2=str(total),
                     leaf_counts=dict(leaves),leaf_instances=sum(leaves.values()),
                     functional_hierarchy_instances=0,unpriced_leaf_instances=0,unmapped_memory_cells=0,
                     is_test_fixture=True,not_a_cpu_result=True,includes_axi_adapter=False,
                     settings=dict(clock_period_ns=2.0,parameters=parameters),netlist_sha256=digest(case/'mapped.v'),
                     libraries=[dict(path=str(lib),sha256=digest(lib)) for lib in raw_libs])
        (case/'area_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
        (case/'run_manifest.json').write_text(json.dumps(dict(source_sha256=frozen,
            source_snapshot_root=str(snapshot),not_a_cpu_result=True,settings=audit['settings']),indent=2)+'\n')
        del design
        print(f'AREA standalone ROB bank{mode}: {total} um2; NOT CPU',flush=True)
        subprocess.run([sys.executable,str(ROOT/'tools/run_course_full_timing.py'),str(case),
                        '--clock-port','clk_i','--reset-port','reset_i'],env=env,check=True)
        check()
        timing = json.loads((case/'full_timing_audit.json').read_text())
        if not timing['not_a_cpu_result'] or timing['omitted_memory_boundaries']:
            raise SystemExit('Standalone ROB timing scope changed')
        results.append(dict(parameters=parameters,area_um2=str(total),
                            netlist_sha256=audit['netlist_sha256'],sram_instances=0,
                            estimated_fmax_mhz=timing['estimated_fmax_mhz'],
                            minimum_period_ns=timing['minimum_period_ns']))
    check()
    (out/'report.json').write_text(json.dumps(dict(status='COMPLETE',not_a_cpu_result=True,
        integrated_into_cpu=False,compiled_origins=origins,snapshot_sha256=frozen,
        yosys_sha256=digest(yosys),results=results,
        scope='Complete actual standalone ROB, all original ports; NOT CPU PPA or IPC'),indent=2)+'\n')
    print('COMPLETE two complete actual ROB component PPA profiles; NOT CPU',flush=True)


if __name__ == '__main__':
    main()
