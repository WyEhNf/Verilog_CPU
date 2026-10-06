"""Validate nested census against installed Yosys, malformed inputs, and a real CPU."""
import argparse
from collections import Counter
import copy
import json
import os
from pathlib import Path
import subprocess

import verify_course_axi_area as old
import verify_course_axi_area_nested as new

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    out = a.outdir.resolve()
    assert not out.exists()
    out.mkdir(parents=True)
    fixture = out/'nested.v'
    fixture.write_text('''module leaf(input a,b, output y); assign y=a&b; endmodule
module middle(input a,b, output [1:0] y);
leaf first(a,b,y[0]); leaf second(a,b,y[1]); endmodule
module student_top(input a,b, output [3:0] y);
middle first(a,b,y[1:0]); middle second(a,b,y[3:2]); endmodule
''')
    script, stats, log = out/'fixture.ys', out/'fixture.json', out/'fixture.log'
    quote = lambda p: '"'+p.as_posix()+'"'
    script.write_text('read_verilog '+quote(fixture)+'\nhierarchy -check -top student_top\nproc\ntee -o '+quote(stats)+' stat -json -top student_top\n')
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite/'bin/yosys.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    with log.open('w') as stream:
        subprocess.run([str(yosys),'-T','-s',str(script)], env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    measured = json.loads(stats.read_text())
    leaves, hierarchy = new.expand_stat_census(measured)
    assert leaves == Counter({'$and':4}), leaves
    assert Counter({k.removeprefix('\\'):v for k,v in hierarchy.items()}) == Counter(middle=2,leaf=4), hierarchy
    assert measured['design']['num_cells'] == 4 and measured['design']['num_submodules'] == 2
    try:
        old.expand_stat_census(measured)
    except AssertionError as error:
        original_failure = str(error)
    else:
        raise AssertionError('Original defect not reproduced on the nested fixture')
    assert original_failure == 'Global expanded type census mismatch'
    cases = []

    def reject(name, mutate):
        damaged = copy.deepcopy(measured)
        mutate(damaged)
        try:
            new.expand_stat_census(damaged)
        except AssertionError as error:
            cases.append(dict(name=name,status='REJECTED',reason=str(error)))
        else:
            raise AssertionError('Malformed census was accepted: '+name)

    def module(d, name):
        return next(v for k,v in d['modules'].items() if k.removeprefix('\\') == name)

    reject('missing_physical_leaf',lambda d:d['design']['num_cells_by_type'].__setitem__('$and',3))
    reject('wrong_total_leaves',lambda d:d['design'].__setitem__('num_cells',3))
    reject('wrong_direct_instances',lambda d:module(d,'student_top').__setitem__('num_submodules',3))
    reject('global_nested_instead_of_direct_total',lambda d:d['design'].__setitem__('num_submodules',6))
    reject('unmapped_memory',lambda d:module(d,'leaf').__setitem__('num_memory_bits',1))
    reject('unreachable_functional_module',lambda d:d['modules'].__setitem__('\\orphan',copy.deepcopy(module(d,'leaf'))))
    reject('zero_cell_multiplicity',lambda d:module(d,'leaf')['num_cells_by_type'].__setitem__('$and',0))
    reject('fractional_cell_multiplicity',lambda d:module(d,'leaf')['num_cells_by_type'].__setitem__('$and',1.5))
    real = Path('F:/CPU2026Integration/r64p64rs12lsq16_cdb2_fixed_functional_hierarchy_20261003/area')
    real_stats = json.loads((real/'stat.json').read_text())
    real_leaves, real_hierarchy = new.expand_stat_census(real_stats)
    assert sum(real_leaves.values()) == 495640 and sum(real_hierarchy.values()) == 85
    assert sum(v for k,v in real_leaves.items() if k.startswith('fakeram_asap7_')) == 37
    baseline = Path('F:/CPU2026Integration/r64p64rs12lsq16_cdb2_legal_addi_fix_20261003/area')
    baseline_stats = json.loads((baseline/'stat.json').read_text())
    assert old.expand_stat_census(baseline_stats) == new.expand_stat_census(baseline_stats)
    inputs = [Path(__file__),Path(old.__file__),Path(new.__file__),yosys,fixture,script,stats,log,
              real/'stat.json',baseline/'stat.json']
    report = dict(status='VERIFIED', original_failure_reproduced=original_failure,
                  fixture_physical_leaves=4,fixture_all_hierarchy_instances=6,fixture_top_direct_instances=2,
                  negative_cases=cases, real_cpu_leaves=sum(real_leaves.values()),real_cpu_sram_instances=37,
                  real_cpu_all_hierarchy_instances=85,original_fixed_baseline_census_unchanged=True,
                  no_frozen_inputs_modified=True,input_sha256={str(p.resolve()):old.sha256(p) for p in inputs})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='input_sha256'},indent=2))


if __name__ == '__main__':
    main()
