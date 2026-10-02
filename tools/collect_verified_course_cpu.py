"""Bind native correctness, IPC, complete area and SRAM timing to one CPU.

Recheck actual frozen build identity, original driver observation-only change,
all 29 authorized programs, raw-price area audit and every timing input hash.
This is the course post-synthesis ideal-clock model, not place-and-route.
"""
import argparse
import json
import math
from pathlib import Path
import re

from verify_course_axi_area import sha256, verify


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--area',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    root,source,area=args.directory.resolve(),args.source_root.resolve(),args.area.resolve()
    assert not args.out.exists(), 'Preserve existing verified result'
    inputs={}
    def record(path,expected=None):
        path=Path(path).resolve()
        value=sha256(path)
        assert expected is None or value==expected.lower(), 'Changed input: '+str(path)
        assert str(path) not in inputs or inputs[str(path)]==value
        inputs[str(path)]=value
    build_path=root/'build/build_manifest.json'
    build=read(build_path);record(build_path)
    assert build['format']=='course-axi-frozen-build-v1'
    for name,expected in build['source_sha256'].items():
        record(source/name,expected)
    record(build['executable'],build['executable_sha256'])
    record(build['generated_driver'],build['generated_driver_sha256'])
    original=(source/'.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
    observed=Path(build['generated_driver']).read_text()
    observation='        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
    assert observed.count(observation)==1 and observed.replace(observation,'')==original
    defaults={k:int(v) for k,v in re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)',
        (source/'rtl/course/student_top.v').read_text().split(') (',1)[0])}
    settings=defaults|build['parameter_overrides']
    reports={}
    for suite,count in dict(benchmark=6,basic=5,simulator=17,boundary=1).items():
        path=root/(suite+'.json');record(path);report=read(path)
        assert report['status']=='COMPLETE' and report['suite']==suite and report['pi_excluded']
        assert Path(report['build_manifest']).resolve()==build_path
        assert Path(report['evaluated_source_root']).resolve()==source
        assert len(report['results'])==len({r['name'] for r in report['results']})==count
        memory=report['external_memory']
        assert memory['latency_cycles']==20 and memory['external_ram_bytes']==268435456
        assert memory['word_bytes']==4 and memory['shared_ar_r'] and memory['exit_at_b_handshake']
        for name,expected in report['source_sha256'].items():
            record(name,expected)
        for row in report['results']:
            assert row['status']=='passed' and row['return_u32']==row['expected_u32']
            assert row['cycles']>0 and row['instret']>0
            assert math.isclose(row['ipc'],row['instret']/row['cycles'],rel_tol=1e-12)
        assert sum(r['cycles'] for r in report['results'])==report['total_cycles']
        assert sum(r['instret'] for r in report['results'])==report['total_instret']
        geomean=math.exp(sum(math.log(r['instret']/r['cycles']) for r in report['results'])/count)
        assert math.isclose(geomean,report['geomean_ipc'],rel_tol=1e-12)
        reports[suite]=report
    assert {r['name'] for r in reports['benchmark']['results']}=={'median','multiply','qsort','rsort','towers','vvadd'}
    manifest=read(area/'run_manifest.json');record(area/'run_manifest.json')
    assert Path(manifest['build_manifest']).resolve()==build_path
    assert manifest['build_manifest_sha256']==sha256(build_path)
    assert manifest['executable_sha256'].lower()==build['executable_sha256'].lower()
    assert manifest['settings']['parameters']==settings
    assert manifest['settings']['parameter_overrides']==build['parameter_overrides']
    checked=verify(area)
    assert checked['status']=='VERIFIED' and checked['settings']==manifest['settings']
    timing=read(area/'full_timing_audit.json');record(area/'full_timing_audit.json')
    assert timing['status']=='COMPLETE' and not timing['not_a_cpu_result'] and not timing['is_test_fixture']
    assert timing['includes_sram'] and timing['omitted_memory_boundaries']==0
    assert timing['netlist_sha256']==checked['netlist_sha256']==sha256(area/'mapped.v')
    assert timing['clock_model']=='ideal' and timing['interconnect']=='no_parasitics'
    assert timing['clock_port']=='clock' and timing['clock_uncertainty_ns']==0.05
    assert timing['input_delay_ns']==timing['output_delay_ns']==0.2 and timing['output_load_ff']==5.0
    assert math.isclose(timing['estimated_fmax_mhz'],1000/timing['minimum_period_ns'],rel_tol=1e-12)
    for name,expected in timing['source_sha256'].items():
        record(name,expected)
    for name in ['area_audit.json','design.json','stat.json','mapped.v','critical_paths.json','timing_values.json']:
        record(area/name)
    record(__file__)
    ipc=reports['benchmark']['geomean_ipc']
    result=dict(status='VERIFIED',directory=str(root),evaluated_source_root=str(source),
                scope=__doc__,all_correctness_cases=29,parameters=settings,
                area=checked['area'],sram_instances=checked['sram_instances'],leaf_instances=checked['leaf_instances'],
                geomean_ipc=ipc,minimum_period_ns=timing['minimum_period_ns'],fmax_mhz=timing['estimated_fmax_mhz'],
                netlist_sha256=checked['netlist_sha256'],input_sha256=inputs,
                tier3_checks=dict(area=float(checked['area']['area_um2'])<=36000,
                                  ipc=ipc>=1.0985,frequency=timing['estimated_fmax_mhz']>=300))
    result['tier3_achieved']=all(result['tier3_checks'].values())
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','all_correctness_cases','area','sram_instances','geomean_ipc','fmax_mhz','tier3_checks','tier3_achieved']},indent=2))


if __name__=='__main__':
    main()
