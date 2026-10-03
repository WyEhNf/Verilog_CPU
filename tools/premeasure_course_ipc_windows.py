"""Run the six original course IPC cases once while STA installation finishes."""
import json
import os
from pathlib import Path
import subprocess
import sys
from prebuild_course_windows import ROOT, sha

assert os.name == 'nt'
config = json.loads((ROOT/'tools/course_windows_config.json').read_text())
source = Path(config['source'])
manifest = json.loads(Path(config['source_manifest']).read_text())
for name, expected in manifest['snapshot_sha256'].items():
    assert sha(source/name) == expected, name
build = json.loads((Path(config['native_build_path'])/'build_identity.json').read_text())
assert build['status'] == 'COMPLETE'
assert build['source_manifest_sha256'] == sha(config['source_manifest'])
assert build['verilator_sha256'] == sha(config['verilator'])
assert build['executable_sha256'] == sha(build['executable'])
env = dict(os.environ)
env['PATH'] = config['runtime_bin']+';'+config['build_bin']+';'+env['PATH']
version = subprocess.check_output([config['verilator'], '--version'], env=env, text=True)
assert 'Verilator 5.020' in version
framework = source/'.deps/RISC-V-CPU-2026'
out = Path(config['native_ipc_path'])
assert not out.exists()
out.mkdir()
command = [sys.executable, str(framework/'scripts/testcase.py'), '--kind', 'perf',
           '--testcases', str(framework/'testcases'), '--sim', build['executable'], '--latency', '10']
(out/'identity.json').write_text(json.dumps(dict(status='PREPARED', command=command))+'\n')
print('START six official course perf cases, native Windows, latency=10', flush=True)
with (out/'perf.log').open('w', encoding='utf-8') as stream:
    result = subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
identity = dict(status='COMPLETE' if result.returncode == 0 else 'FAILED', command=command,
    latency=10, source_manifest_sha256=sha(config['source_manifest']),
    executable_sha256=build['executable_sha256'], verilator_sha256=build['verilator_sha256'],
    log=str(out/'perf.log'), log_sha256=sha(out/'perf.log'), returncode=result.returncode,
    official_scripts_unmodified=True, official_sim_cpp_unmodified=True)
(out/'identity.json').write_text(json.dumps(identity, indent=2)+'\n')
print((out/'perf.log').read_text(), flush=True)
raise SystemExit(result.returncode)
