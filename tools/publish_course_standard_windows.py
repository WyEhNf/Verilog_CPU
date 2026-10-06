"""Publish the completed native course measurement without rerunning tests."""
import json
import os
from pathlib import Path
from prebuild_course_windows import ROOT, sha

assert os.name == 'nt'
config = json.loads((ROOT/'tools/course_windows_config.json').read_text())
out = Path(config['out'])
result = json.loads((out/'result.json').read_text())
assert result['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
assert result['environment'] == 'WINDOWS_NATIVE'
assert result['official_perf_expected_results_passed']
manifest = json.loads(Path(config['source_manifest']).read_text())
for name, expected in manifest['snapshot_sha256'].items():
    assert sha(Path(config['source'])/name) == expected, name
for name, expected in manifest['original_worktree_sha256'].items():
    assert sha(ROOT/name) == expected, name
tools = json.loads((Path(config['tools_root'])/'toolchain_manifest.json').read_text())
for name in ('yosys', 'abc', 'sta', 'verilator'):
    assert sha(config[name]) == tools['tool_sha256'][name], name
report = json.loads((out/'synth/opt/report.json').read_text())
assert len(report['area']['sram_instances']) == 37
assert abs(sum(row['area_um2'] for row in report['area']['sram_instances'])-
           report['area']['sram_area_um2']) < 1e-6
old = json.loads(Path(manifest['profile_path']).read_text())
identity = json.loads((out/'measurement_identity.json').read_text())
identity.update(status='COMPLETE', result_sha256=sha(out/'result.json'),
                official_report_sha256=sha(out/'synth/opt/report.json'), ipc_sha256=sha(out/'ipc.json'))
(out/'measurement_identity.json').write_text(json.dumps(identity, indent=2)+'\n')
evidence = [out/'result.json', out/'measurement_identity.json', out/'synth/opt/report.json',
            out/'ipc.json', Path(config['source_manifest']),
            Path(config['tools_root'])/'toolchain_manifest.json',
            Path(config['native_build_path'])/'build_identity.json']
profile = dict(status='CURRENT_ADOPTED_CPU_COURSE_STANDARD_WINDOWS_MEASURED',
    source_root=str(ROOT), frozen_source=config['source'],
    source_sha256=manifest['original_worktree_sha256'],
    parameter_overrides=manifest['parameter_overrides'],
    effective_parameters=old['effective_parameters'],
    normal_integer_pipeline_stages=old['normal_integer_pipeline_stages'],
    geomean_ipc=result['ipc'], fmax_mhz=result['fmax_mhz'],
    minimum_period_ns=result['minimum_period_ns'],
    area={k:report['area'][k] for k in ('area_um2','logic_area_um2','combinational_area_um2',
                                     'sequential_area_um2','sram_area_um2')},
    sram_instances=37, latency=10, ipc_numerator='official metrics.json',
    tools=tools, measurement_result=str(out/'result.json'),
    netlist_sha256=sha(out/'synth/opt/mapped.v'),
    official_perf_cases_passed=6, correctness_suite_not_run=True,
    frequency_target_reached=result['fmax_mhz'] >= 300,
    tier3_achieved=result['tier3_numeric_requirements_met'],
    previous_profile_preserved=manifest['profile_path'],
    evidence_sha256={str(path):sha(path) for path in evidence})
target = ROOT/'build/cpu2026/verified_course_standard_windows_profile_20261003.json'
target.write_text(json.dumps(profile, indent=2)+'\n')
print(json.dumps(dict(profile=str(target), ipc=result['ipc'], fmax_mhz=result['fmax_mhz'],
                     area_um2=result['area_um2'], sram_instances=37,
                     current_source_hash_mismatches=0), indent=2))
