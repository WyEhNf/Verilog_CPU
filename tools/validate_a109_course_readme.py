"""Validate the frozen A109 through the unmodified course Makefile (Pi excluded)."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUN = Path('F:/CPU2026CourseRuns/ER1_A109_tier3_20261006')
SOURCE = RUN / 'source'
COURSE = SOURCE / '.deps/RISC-V-CPU-2026'
OUT = Path('F:/CPU2026CourseRuns/A109_readme_interface_no_pi_20261006')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def check_source():
    manifest = read(RUN / 'source_manifest.json')
    for name, digest in manifest['snapshot_sha256'].items():
        assert sha(SOURCE / name) == digest, name
    return manifest


def environment():
    config = read(RUN / 'course_windows_config.json')
    env = dict(os.environ)
    env.update(PYTHONUNBUFFERED='1', VERILATOR_ROOT=Path(config['tools_root']).as_posix() + '/verilator/share/verilator',
               SHELL=config['build_bin'] + '/sh.exe', TEMP='F:/CPU2026Temp', TMP='F:/CPU2026Temp')
    env['PATH'] = ';'.join([config['runtime_bin'], config['build_bin'],
                          str(ROOT / '.deps/oss-cad-suite-install/oss-cad-suite/bin'),
                          str(ROOT / '.deps/oss-cad-suite-install/oss-cad-suite/lib'), env['PATH']])
    return config, env


def command_run(name, command, cwd=SOURCE, env=None):
    print('START ' + name, flush=True)
    started = datetime.now(timezone.utc).isoformat()
    with (OUT / (name + '.log')).open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=cwd, env=env or environment()[1], stdout=stream, stderr=subprocess.STDOUT)
    record = dict(command=command, cwd=str(cwd), returncode=result.returncode, started_at=started,
                  ended_at=datetime.now(timezone.utc).isoformat(), log=str(OUT / (name + '.log')),
                  log_sha256=sha(OUT / (name + '.log')))
    write(OUT / (name + '.command.json'), record)
    print(('PASS ' if not result.returncode else 'FAIL ') + name, flush=True)
    return record


def make(target, *options):
    config, _ = environment()
    return [config['build_bin'] + '/make.exe', '-f', (COURSE / 'Makefile').as_posix(), target,
            'CONFIG=' + (OUT / 'config.mk').as_posix(), *options]


def prepare():
    assert not OUT.exists(), 'Preserve earlier runs; choose a fresh output directory'
    OUT.mkdir(parents=True)
    manifest = check_source()
    c, env = environment()
    values = dict(APPIMAGE='', PYTHON=Path(sys.executable).as_posix(),
                  VERILATOR=Path(c['verilator_build_driver']).as_posix(),
                  YOSYS=Path(c['yosys']).as_posix(), ABC=Path(c['abc']).as_posix(), STA=Path(c['sta']).as_posix(),
                  ASAP7_LIB=Path(c['asap7_lib']).as_posix(), CXX=c['runtime_bin'] + '/g++.exe',
                  AR=c['runtime_bin'] + '/ar.exe', BUILD_MAKE=c['build_bin'] + '/make.exe',
                  BUILD=(OUT / 'build').as_posix(), SYNTH_OUT=(OUT / 'synth').as_posix(),
                  TESTCASES=(COURSE / 'testcases').as_posix(), FILELIST='verilog/filelist.f',
                  JOBS='2', LATENCY='10', MAX_CYCLES='10000000')
    (OUT / 'config.mk').write_text('\n'.join(k + ' = ' + v for k, v in values.items()) + '\n', encoding='utf-8')
    # Read the ANSI port declarations independently from their implementation.
    text = (SOURCE / 'rtl/course/student_top.v').read_text()
    declaration = text[text.index(') (') + 3:text.index(');', text.index(') ('))]
    ports = {}
    direction, width = None, None
    for item in declaration.split(','):
        item = item.strip()
        match = re.fullmatch(r'(input|output)\s+wire\s*(?:\[(\d+):0\])?\s*(\w+)', item)
        if match:
            direction = match[1]
            width = int(match[2]) + 1 if match[2] else 1
            name = match[3]
        else:
            assert re.fullmatch(r'\w+', item), item
            name = item
        ports[name] = dict(direction=direction, width=width)
    expected = {name:dict(direction=direction, width=width) for direction, width, names in [
        ('input', 1, 'clock reset arready rvalid awready wready bvalid'),
        ('input', 32, 'rdata'), ('input', 2, 'rresp bresp'),
        ('output', 1, 'arvalid rready awvalid wvalid bready'),
        ('output', 32, 'araddr awaddr wdata'), ('output', 4, 'wstrb')] for name in names.split()}
    assert all(ports.get(k) == v for k, v in expected.items()), (ports, expected)
    listed = [(SOURCE / 'verilog' / line.split('#')[0].strip()).resolve()
              for line in (SOURCE / 'verilog/filelist.f').read_text().splitlines() if line.split('#')[0].strip()]
    assert len(set(listed)) == len(listed) and all(p.is_file() for p in listed)
    assert (SOURCE / 'rtl/course/student_top.v').resolve() in listed
    candidate = read(Path(manifest['candidate']) / 'candidate.json')
    assert sha(Path(manifest['candidate']) / 'candidate.json') == manifest['candidate_manifest_sha256']
    for name, digest in candidate['source_sha256'].items():
        assert sha(SOURCE / name) == digest, name
    write(OUT / 'interface_audit.json', dict(status='PASS', source_manifest_sha256=sha(RUN / 'source_manifest.json'),
          frozen_input_count=len(manifest['snapshot_sha256']), candidate_source_count=len(candidate['source_sha256']),
          listed_rtl_count=len(listed), required_ports=expected,
          extra_output_ports={k:v for k,v in ports.items() if k not in expected},
          bridge_parameters={k:manifest['parameter_overrides'][k] for k in (
              'READ_LINES', 'WRITE_LINES', 'WORD_QUEUE', 'AXI_READ_PAYLOAD_SRAM', 'AXI_RESPONSE_FIFO_DEPTH')},
          source=str(SOURCE), user_excluded_cases=['correctness_pi'],
          official_scripts_unmodified=True, rtl_modified=False))
    assert command_run('make_help', make('help'), env=env)['returncode'] == 0
    print('PREPARED ' + str(OUT), flush=True)


def build():
    check_source()
    c, env = environment()
    result = command_run('make_build', make('build'), env=env)
    # Verilator 5.020 expects a Windows time-zero fallback when its weak
    # sc_time_stamp symbol is unavailable. Keep the official sim.cpp unchanged.
    if result['returncode']:
        log = (OUT / 'make_build.log').read_text(errors='replace')
        assert 'sc_time_stamp' in log or 'ar.exe' in log, log[-4000:]
        shim = OUT / 'windows_time_zero.o'
        assert command_run('build_time_zero', [c['runtime_bin'] + '/g++.exe', '-O2', '-c',
                           str(ROOT / 'tools/verilator_windows_time_zero.cpp'), str('-o'), str(shim)], env=env)['returncode'] == 0
        resume = [c['build_bin'] + '/make.exe', '-C', (OUT / 'build/obj').as_posix(), '-f', 'Vstudent_top.mk', '-j2',
                  'CXX=' + c['runtime_bin'] + '/g++.exe', 'LINK=' + c['runtime_bin'] + '/g++.exe',
                  'AR=' + c['runtime_bin'] + '/ar.exe', 'PYTHON3=' + Path(sys.executable).as_posix(),
                  'VM_USER_LDLIBS=' + shim.as_posix()]
        assert command_run('make_build_windows_link', resume, env=env)['returncode'] == 0
    binary = next(p for p in [OUT / 'build/sim', OUT / 'build/sim.exe'] if p.is_file())
    check_source()
    write(OUT / 'build_identity.json', dict(status='PASS', executable=str(binary), executable_sha256=sha(binary),
          source_manifest_sha256=sha(RUN / 'source_manifest.json'), official_sim_cpp_sha256=sha(COURSE / 'scripts/sim.cpp'),
          official_build_py_sha256=sha(COURSE / 'scripts/build.py'), native_verilator_version=read(RUN / 'native_build/build_identity.json')['version'],
          native_verilator_sha256=sha(c['verilator']), windows_link_fallback_used=bool(result['returncode'])))


def tests():
    check_source()
    identity = read(OUT / 'build_identity.json')
    sim = Path(identity['executable'])
    assert sha(sim) == identity['executable_sha256']
    cases = sorted(p for p in (COURSE / 'testcases').glob('correctness_*') if p.is_dir() and p.name != 'correctness_pi')
    assert len(cases) == 18
    def one_case(case):
        command = make('test', 'SIM=' + sim.as_posix(), 'Case=' + case.name)
        record_path = OUT / (case.name + '.command.json')
        prior = read(record_path) if record_path.exists() else None
        if prior and prior['returncode'] == 0 and prior['command'] == command and sha(prior['log']) == prior['log_sha256']:
            record = prior
            print('REUSE verified ' + case.name, flush=True)
        else:
            log_path = OUT / (case.name + '.log')
            if log_path.exists() and not prior:
                (OUT / (case.name + '.interrupted.log')).write_bytes(log_path.read_bytes())
            record = command_run(case.name, command)
        text = Path(record['log']).read_text()
        cycles = re.search(r'PASS cycles=(\d+)', text)
        return dict(name=case.name, status='PASS' if record['returncode'] == 0 and cycles else 'FAIL',
                            cycles=int(cycles[1]) if cycles else None, expected=(case / 'expected.txt').read_text().strip(),
                            program_sha256=sha(case / 'program.data'), expected_sha256=sha(case / 'expected.txt'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one_case, cases))
    perf = command_run('make_perf', make('perf', 'SIM=' + sim.as_posix(), 'MAX_CYCLES=1000000'))
    scores = []
    for name, instructions, cycles in re.findall(r'^(perf_\S+)\s+(\d+)\s+(\d+)\s+[0-9.]+$',
                                                (OUT / 'make_perf.log').read_text(), re.MULTILINE):
        scores.append(dict(name=name, instructions=int(instructions), cycles=int(cycles), ipc=int(instructions)/int(cycles)))
    assert len(scores) == 6 and not perf['returncode']
    single = command_run('make_run_wave_log', make('run', 'SIM=' + sim.as_posix(),
                         'PROGRAM=' + (COURSE / 'testcases/correctness_add_to_100/program.data').as_posix(),
                         'EXPECTED=5050', 'WAVE=' + (OUT / 'trace.vcd').as_posix(), 'LOG=' + (OUT / 'run.log').as_posix()))
    check_source()
    assert sha(sim) == identity['executable_sha256']
    write(OUT / 'tests.json', dict(status='PASS' if all(r['status'] == 'PASS' for r in results) and not single['returncode'] else 'FAIL',
          excluded_cases=['correctness_pi'], pi_executed=False, correctness=results, performance=scores,
          ipc_geomean=math.exp(sum(math.log(r['ipc']) for r in scores)/len(scores)),
          latency=10, correctness_max_cycles=10000000, performance_max_cycles=1000000,
          make_run=single, waveform_bytes=(OUT / 'trace.vcd').stat().st_size,
          source_manifest_sha256=sha(RUN / 'source_manifest.json'), executable_sha256=identity['executable_sha256']))
    assert all(r['status'] == 'PASS' for r in results) and not single['returncode']


def protocols():
    check_source()
    out = OUT / 'protocol'
    out.mkdir(exist_ok=True)
    original = (ROOT / 'tb/unit/rv32_axi_lite_bridge_tb.v').read_text()
    code = original.replace('parameter integer RESPONSE_FIFO_DEPTH = 0,',
                            'parameter integer READ_PAYLOAD_SRAM = 1,\n    parameter integer ERROR_RESPONSE = 2,\n    parameter integer RESPONSE_FIFO_DEPTH = 2,')
    code = code.replace('.WORD_QUEUE(WORD_QUEUE), .RESPONSE_FIFO_DEPTH', '.WORD_QUEUE(WORD_QUEUE), .READ_PAYLOAD_SRAM(READ_PAYLOAD_SRAM), .RESPONSE_FIFO_DEPTH')
    code = code.replace('repeat (3) @(negedge clock)', 'repeat (5) @(negedge clock)')
    code = code.replace('== 2 ? 2 : 0', '== 2 ? ERROR_RESPONSE : 0').replace('== 3 ? 2 : 0', '== 3 ? ERROR_RESPONSE : 0')
    code = code.replace('if (!reset) begin\n            cycle <=',
                        'if (reset && (arvalid || awvalid || wvalid || rready || bready)) $fatal(1, "AXI active under reset");\n        if (!reset) begin\n            cycle <=')
    code = code.replace('$display("PASS: AXI shared', '$display("COVER read_words=%0d write_words=%0d exit_words=%0d AW_first=%0d W_first=%0d", read_words, write_words, exit_words, aw_first, w_first);\n        $display("PASS: AXI shared')
    tb = out / 'rv32_axi_lite_bridge_tb.v'
    tb.write_text(code)
    c, env = environment()
    env['MAKE'] = c['build_bin'] + '/make.exe'
    shim = out / 'windows_time_zero.o'
    assert not command_run('protocol_time_zero', [c['runtime_bin'] + '/g++.exe', '-O2', '-c',
                          str(ROOT / 'tools/verilator_windows_time_zero.cpp'), '-o', str(shim)], env=env)['returncode']
    compiler = c['verilator_build_driver']
    sources = [SOURCE / 'rtl/course/rv32_axi_lite_bridge.v', SOURCE / 'rtl/common/rv32_asap7_fanout.v',
               COURSE / 'scripts/ram/sram_fakeram.sv']
    results = []
    def compile_test(top, name, fixture, overrides):
        image = out / (name + '.exe')
        makeflags = ' '.join([k + '=' + v for k,v in dict(CXX=c['runtime_bin'] + '/g++.exe',
            LINK=c['runtime_bin'] + '/g++.exe', AR=c['runtime_bin'] + '/ar.exe',
            PYTHON3=Path(sys.executable).as_posix(), VM_USER_LDLIBS=shim.as_posix()).items()])
        command = [compiler, '--binary', '--timing', '--assert', '-Wno-fatal', '--top-module', top,
                   '--Mdir', (out / (name + '_posix_obj')).as_posix(), '-o', image.as_posix(), '-j', '2',
                   '-CFLAGS', '-std=c++17', '-MAKEFLAGS', makeflags]
        command += ['-G' + k + '=' + str(v) for k,v in overrides.items()]
        command += [fixture.as_posix()] + [p.as_posix() for p in sources]
        assert not command_run(name + '_verilator_posix_compile', command, env=env)['returncode']
        return image
    for response, queue in ((2, 16), (3, 16), (2, 4)):
        name = f'bridge_sram1_fifo2_r8_w4_q{queue}_error{response}'
        overrides = dict(READ_LINES=8, WRITE_LINES=4, WORD_QUEUE=queue, READ_PAYLOAD_SRAM=1, RESPONSE_FIFO_DEPTH=2, ERROR_RESPONSE=response)
        image = compile_test('rv32_axi_lite_bridge_tb', name, tb, overrides)
        record = command_run(name, [str(image)], env=env)
        text = Path(record['log']).read_text()
        assert not record['returncode'] and 'PASS:' in text and not re.search(r'FATAL:|FAIL:|ERROR:', text)
        results.append(dict(name=name, status='PASS', parameters=overrides, coverage=text.strip()))
    for seed in (17, 97):
        name = f'response_fifo_d2_seed{seed}'
        image = compile_test('rv32_axi_response_fifo_tb', name, ROOT / 'tb/unit/rv32_axi_response_fifo_tb.v', dict(DEPTH=2, SEED=seed))
        record = command_run(name, [str(image)], env=env)
        text = Path(record['log']).read_text()
        assert not record['returncode'] and 'PASS:' in text and not re.search(r'FATAL:|FAIL:|ERROR:', text)
        results.append(dict(name=name, status='PASS', coverage=text.strip()))
    check_source()
    write(OUT / 'protocols.json', dict(status='PASS', results=results, fixture_sha256=sha(tb),
          tested_rtl_sha256={str(p):sha(p) for p in sources},
          scope='Directed bridge and FIFO checks; not a formal proof of all possible AXI traces'))


def synth():
    check_source()
    assert not command_run('make_synth_opt', make('synth', 'MODE=opt', 'CLOCK_PERIOD_NS=2.0'))['returncode']
    check_source()
    report = read(OUT / 'synth/opt/report.json')
    write(OUT / 'synthesis_summary.json', dict(status='PASS', area=report['area'], timing=report['timing'],
          source_manifest_sha256=sha(RUN / 'source_manifest.json'), report_sha256=sha(OUT / 'synth/opt/report.json')))


def structural():
    """Check the bridge at gate/bit granularity, stopping at sequential cells."""
    check_source()
    c, env = environment()
    netlist = OUT / 'bridge_gate_dependencies.json'
    script = OUT / 'bridge_dependencies.ys'
    sources = [SOURCE / 'rtl/common/rv32_asap7_fanout.v', SOURCE / 'rtl/course/rv32_axi_lite_bridge.v']
    bridge = sources[1].read_text()
    port_block = bridge[bridge.index(') (') + 3:bridge.index(');', bridge.index(') ('))]
    names = [re.search(r'(\w+)\s*$', part.strip())[1] for part in port_block.split(',')]
    wrapper = OUT / 'a109_axi_bridge_check.v'
    wrapper.write_text('module a109_axi_bridge_check (\n' + port_block + '\n);\n' +
        'rv32_axi_lite_bridge #(.READ_LINES(8), .WRITE_LINES(4), .WORD_QUEUE(16), .READ_PAYLOAD_SRAM(1), .RESPONSE_FIFO_DEPTH(2)) dut (\n' +
        ',\n'.join('.' + name + '(' + name + ')' for name in names) + ');\nendmodule\n')
    sources.append(wrapper)
    commands = ['read_verilog -sv -D SYNTHESIS "' + p.as_posix() + '"' for p in sources]
    commands += ['read_verilog -lib -sv -D SYNTHESIS "' + (COURSE / 'scripts/ram/sram_fakeram.sv').as_posix() + '"',
                 'hierarchy -top a109_axi_bridge_check',
                 'proc', 'select *', 'setattr -mod -unset keep_hierarchy', 'setattr -unset keep_hierarchy',
                 'flatten', 'opt', 'techmap', 'opt', 'scc -expect 0', 'write_json "' + netlist.as_posix() + '"']
    script.write_text('\n'.join(commands) + '\n')
    assert not command_run('bridge_structural_bit_dependencies', [c['yosys'], '-s', script.as_posix()], env=env)['returncode']
    module = read(netlist)['modules']['a109_axi_bridge_check']
    drivers = {}
    stopped = set()
    for cell in module['cells'].values():
        kind = cell['type']
        outputs = [b for p,bits in cell['connections'].items() if cell['port_directions'][p] == 'output' for b in bits if isinstance(b, int)]
        if not outputs:
            continue
        if re.search(r'(DFF|SDFF|DLATCH|FF)', kind, re.IGNORECASE) or 'sram_fakeram' in kind:
            stopped.add(kind)
            continue
        assert kind.startswith('$_'), kind
        inputs = {b for p,bits in cell['connections'].items() if cell['port_directions'][p] == 'input' for b in bits if isinstance(b, int)}
        for b in outputs:
            assert b not in drivers, (b, kind)
            drivers[b] = inputs
    input_bits = {b:name for name,p in module['ports'].items() if p['direction'] == 'input' for b in p['bits']}
    results = {}
    for name in ('araddr', 'arvalid', 'rready', 'awaddr', 'awvalid', 'wdata', 'wstrb', 'wvalid', 'bready'):
        todo, seen = list(module['ports'][name]['bits']), set()
        while todo:
            bit = todo.pop()
            if bit in seen or not isinstance(bit, int):
                continue
            seen.add(bit)
            todo.extend(drivers.get(bit, ()))
        dependencies = sorted({input_bits[b] for b in seen if b in input_bits})
        assert set(dependencies) <= {'reset'}, (name, dependencies)
        results[name] = dependencies
    write(OUT / 'structural.json', dict(status='PASS', combinational_scc_count=0,
          external_combinational_input_dependencies=results, sequential_boundary_cell_types=sorted(stopped),
          netlist_sha256=sha(netlist), source_manifest_sha256=sha(RUN / 'source_manifest.json'),
          scope='Exact A109 AXI bridge; SRAM is treated as its documented synchronous boundary'))


def waveform():
    """Scoreboard settled pre-edge AXI pins in the official make run trace."""
    wanted = set('clock reset araddr arvalid arready rdata rresp rvalid rready awaddr awvalid awready wdata wstrb wvalid wready bresp bvalid bready'.split())
    identifiers, state, stalls = {}, {}, {}
    counts = dict(reset_edges=0, ar=0, r=0, aw=0, w=0, b=0, ar_stalls=0, aw_stalls=0, w_stalls=0)
    aw_queue, w_queue, response_queue = [], [], []
    exit_transfers = []
    def rising(sample):
        assert wanted <= set(sample), wanted - set(sample)
        if sample['reset']:
            counts['reset_edges'] += 1
            assert not any(sample[n] for n in ('arvalid', 'awvalid', 'wvalid', 'rready', 'bready'))
            stalls.clear()
            return
        for channel, payload in [('ar', ('araddr',)), ('aw', ('awaddr',)), ('w', ('wdata', 'wstrb'))]:
            packet = tuple(sample[n] for n in payload)
            if channel in stalls:
                assert sample[channel + 'valid'] and packet == stalls[channel], (channel, packet, stalls[channel])
            if sample[channel + 'valid'] and not sample[channel + 'ready']:
                stalls[channel] = packet
                counts[channel + '_stalls'] += 1
            else:
                stalls.pop(channel, None)
        for channel in ('ar', 'r', 'aw', 'w', 'b'):
            if sample[channel + 'valid'] and sample[channel + 'ready']:
                counts[channel] += 1
                if channel in ('ar', 'aw'):
                    assert sample[channel + 'addr'] & 3 == 0
                if channel == 'aw':
                    aw_queue.append(sample['awaddr'])
                if channel == 'w':
                    w_queue.append((sample['wdata'], sample['wstrb']))
                if channel == 'b':
                    assert response_queue, 'B response without a previously paired AW/W'
                    address, data, mask = response_queue.pop(0)
                    assert sample['bresp'] == 0
                    if address == 0x80000000:
                        assert mask == 15 and data == 5050
                        exit_transfers.append(dict(address=address, data=data, wstrb=mask, bresp=sample['bresp']))
                if channel == 'r':
                    assert sample['rresp'] == 0 and counts['r'] <= counts['ar']
        while aw_queue and w_queue:
            data, mask = w_queue.pop(0)
            response_queue.append((aw_queue.pop(0), data, mask))
    with (OUT / 'trace.vcd').open() as stream:
        in_values, pending = False, {}
        for line in stream:
            line = line.strip()
            if not in_values:
                if line.startswith('$var '):
                    parts = line.split()
                    if parts[4] in wanted and parts[4] not in identifiers.values():
                        identifiers[parts[3]] = parts[4]
                if line.startswith('$enddefinitions'):
                    assert set(identifiers.values()) == wanted
                    in_values = True
                continue
            if line.startswith('#'):
                if pending.get('clock') == 1 and state.get('clock') == 0:
                    rising(state)
                state.update(pending)
                pending = {}
            elif line and line[0] in '01xz':
                if line[1:] in identifiers:
                    assert line[0] in '01', line
                    pending[identifiers[line[1:]]] = int(line[0])
            elif line.startswith('b'):
                value, code = line[1:].split()
                if code in identifiers:
                    assert not re.search('[xz]', value)
                    pending[identifiers[code]] = int(value, 2)
        if pending.get('clock') == 1 and state.get('clock') == 0:
            rising(state)
    assert counts['reset_edges'] == 5 and len(exit_transfers) == 1
    write(OUT / 'waveform_axi.json', dict(status='PASS', program='correctness_add_to_100',
          counters=counts, mmio_exit_b_handshakes=exit_transfers, trace_sha256=sha(OUT / 'trace.vcd'),
          scope='One official full-CPU trace; broad backpressure and error coverage is in the bridge tests'))


def boundary():
    check_source()
    binary = read(OUT / 'build_identity.json')
    assert sha(binary['executable']) == binary['executable_sha256']
    image = ROOT / 'build/images/ram_256m_last_word/ram_256m_last_word.image'
    digest = sha(image)
    record = command_run('make_run_ram_lastword', make('run', 'SIM=' + Path(binary['executable']).as_posix(),
        'PROGRAM=' + image.as_posix(), 'EXPECTED=598', 'MAX_CYCLES=100000', 'LATENCY=10'))
    text = Path(record['log']).read_text()
    match = re.search(r'PASS cycles=(\d+) result=598 expected=598', text)
    assert not record['returncode'] and match and sha(image) == digest
    write(OUT / 'boundary.json', dict(status='PASS', program=str(image), program_sha256=digest,
        expected=598, cycles=int(match[1]), executable_sha256=binary['executable_sha256'],
        source_manifest_sha256=sha(RUN / 'source_manifest.json'), latency=10,
        scope='Existing project program tests the highest 256 MiB RAM word; supplementary to official cases'))


def finalize():
    manifest = check_source()
    names = ['interface_audit', 'build_identity', 'tests', 'protocols', 'structural', 'waveform_axi', 'boundary', 'synthesis_summary']
    records = {name:read(OUT / (name + '.json')) for name in names}
    assert all(r['status'] == 'PASS' for r in records.values())
    manifest_hash = sha(RUN / 'source_manifest.json')
    for name in ('interface_audit', 'build_identity', 'tests', 'structural', 'boundary', 'synthesis_summary'):
        assert records[name]['source_manifest_sha256'] == manifest_hash, name
    for path, digest in records['protocols']['tested_rtl_sha256'].items():
        assert sha(path) == digest, path
    identity, tests = records['build_identity'], records['tests']
    assert sha(identity['executable']) == identity['executable_sha256'] == tests['executable_sha256']
    assert tests['pi_executed'] is False and tests['excluded_cases'] == ['correctness_pi']
    assert len(tests['correctness']) == 18 and len(tests['performance']) == 6
    report = read(OUT / 'synth/opt/report.json')
    assert report['mode'] == 'opt' and report['timing']['timing_analyzed']
    assert records['synthesis_summary']['report_sha256'] == sha(OUT / 'synth/opt/report.json')
    for item in report['inputs']:
        # The framework records paths, their checksums and size.
        if isinstance(item, dict) and 'path' in item and 'sha256' in item:
            assert sha(item['path']) == item['sha256'], item['path']
    area, timing = report['area'], report['timing']
    assert math.isclose(area['area_um2'], sum(area[k] for k in ('combinational_area_um2', 'sequential_area_um2', 'sram_area_um2')), abs_tol=1e-6)
    for item in report['libraries']:
        if isinstance(item, dict) and 'path' in item and 'sha256' in item:
            assert sha(item['path']) == item['sha256'], item['path']
    c, _ = environment()
    installed = read(Path(c['tools_root']) / 'toolchain_manifest.json')
    for name in ('yosys', 'abc', 'sta', 'verilator'):
        assert sha(c[name]) == installed['tool_sha256'][name]
    assert sha(c['verilator_build_driver']) == read(RUN / 'native_build/build_identity.json')['verilator_build_driver_sha256']
    proof_files = [OUT / (name + '.json') for name in names] + [OUT / 'config.mk', OUT / 'run.log', OUT / 'trace.vcd',
        OUT / 'synth/opt/report.json', OUT / 'synth/opt/report.txt', OUT / 'synth/opt/timing.rpt',
        OUT / 'synth/opt/area.json', OUT / 'synth/opt/timing.json', OUT / 'synth/opt/constraints.sdc',
        OUT / 'synth/opt/mapped.v', OUT / 'synth/opt/design.json',
        ROOT / '.deps/RISC-V-CPU-2026/README-ZH.md', ROOT / '.deps/RISC-V-CPU-2026/docs/axi4-lite.md', Path(__file__)]
    proof_files += sorted(OUT.glob('*.command.json')) + sorted(OUT.glob('*.log'))
    proof = dict(status='A109_README_INTERFACE_AND_REQUESTED_TEST_SCOPE_PASS',
        completed_at=datetime.now(timezone.utc).isoformat(), source=str(SOURCE), output=str(OUT),
        source_manifest_sha256=sha(RUN / 'source_manifest.json'), frozen_source_count=len(manifest['snapshot_sha256']),
        rtl_changed=False, pi_executed=False, correctness_passed=18, correctness_failed=0,
        protocol_cases_passed=len(records['protocols']['results']), perf_cases_passed=6,
        ipc_geomean=tests['ipc_geomean'], area_um2=area['area_um2'],
        fmax_mhz=timing['estimated_fmax_mhz'], worst_setup_slack_ns=timing['worst_setup_slack_ns'],
        artifact_sha256={str(p):sha(p) for p in proof_files})
    write(OUT / 'validation.json', proof)
    rows = ['# A109：课程 README 接口检查与测试（跳过 Pi）', '',
        '本次使用已测 A109 冻结快照重新编译、仿真和 opt 综合。接口检查与所请求的仿真测试通过，综合与 STA 执行成功；2 ns 时序约束未满足。Pi 按用户要求未运行。', '',
        f'源码：`{SOURCE.as_posix()}`；产物：`{OUT.as_posix()}`。',
        f'冻结清单 SHA256：`{proof["source_manifest_sha256"]}`；157 个冻结输入和候选的 41 份源码逐一核对。',
        f'新仿真器 SHA256：`{identity["executable_sha256"]}`。未修改 A109 RTL、官方 Makefile、scripts、程序镜像或 Golden 答案。', '',
        '## 顶层与 AXI4-Lite', '',
        '- `student_top` 已列入相对路径 `verilog/filelist.f`；必需的 19 个端口名称、方向、位宽均匹配 README 模板。',
        '- 另有 `debug_instret`、`debug_core_cycles`、`debug_error` 三个观察输出；官方未修改的 sim.cpp 已实际编译并正常运行。',
        '- 高电平复位 5 周期期间 ARVALID/AWVALID/WVALID/RREADY/BREADY 均为 0；外部读写地址按 4 字节对齐。',
        '- 外部 RAM 配置为 256 MiB 小端；最高有效字地址 0x0ffffffc 的既有工程读写/回写边界程序通过，返回 598。',
        '- 发送端 VALID 和载荷在背压期间保持稳定；AW 与 W 可分别先握手，完成配对后等待 B 响应。',
        '- 正确拼接四个 32 位读响应、恢复 I/D 请求身份、传递字节写掩码、跳过零掩码字、聚合 SLVERR/DECERR。',
        '- 按 A109 实际 READ_LINES=8、WRITE_LINES=4、WORD_QUEUE=16、READ_PAYLOAD_SRAM=1、RESPONSE_FIFO_DEPTH=2 检查；另以 WORD_QUEUE=4 加压。',
        '- Yosys 展平到位级门网表后 SCC=0；外部 AXI 输出没有经过组合逻辑依赖 READY、RVALID、BVALID 或响应载荷的路径。SRAM 按课程规定的同步边界处理。',
        '- 完整 CPU 的 add_to_100 波形检查通过：退出地址 0x80000000，WSTRB=0xf，WDATA=5050，在 BVALID/BREADY 握手时确认退出。', '',
        '协议测试为定向仿真和结构检查，不是对所有可能 AXI 时序的形式证明。', '',
        '## 本次实际执行', '',
        '| 项目 | 结果 |', '|---|---|', '| make help | 通过 |',
        '| make build JOBS=2 + Windows 归档/链接续编 | 新构建通过 |', '| make test Case=...（18 项，排除 Pi） | 18/18 |',
        '| make perf（全部六项） | 6/6 |', '| make run + WAVE + LOG | 通过 |',
        '| 256 MiB RAM 最高地址补充测试 | 通过，返回 598 |',
        '| AXI 桥接与响应 FIFO 场景 | 5/5 |', '| AXI 位级组合依赖与环路 | 通过 |',
        '| make synth MODE=opt CLOCK_PERIOD_NS=2.0 | 流程完成，2 ns 时序约束未满足 |', '',
        '正确性 MAX_CYCLES=10000000，性能 MAX_CYCLES=1000000，LATENCY=10；测试 runner 和内存从机均为课程原版。',
        '官方 Makefile 无排除单项的参数，因此逐个执行 make test Case=...，没有执行包含 Pi 的全量 make test。', '',
        '## 正确性用例', '', '| 测试点 | 周期 | 标准答案 | 结果 |', '|---|---:|---:|---|']
    rows += [f'| {r["name"]} | {r["cycles"]} | {r["expected"]} | {r["status"]} |' for r in tests['correctness']]
    rows += ['', '`correctness_pi`：按要求跳过，本报告不将其计入通过项。', '',
        '## 性能', '', '| 基准 | 动态指令数 | 周期 | IPC |', '|---|---:|---:|---:|']
    rows += [f'| {r["name"]} | {r["instructions"]} | {r["cycles"]} | {r["ipc"]:.12f} |' for r in tests['performance']]
    rows += [f'| GEOMEAN | | | {tests["ipc_geomean"]:.12f} |', '',
        '动态指令数采用课程 metrics.json；周期来自新仿真器，IPC 和 GEOMEAN 按官方定义计算。', '',
        '## 新综合与静态时序分析', '', '| 指标 | 结果 |', '|---|---:|',
        f'| 组合逻辑面积 | {area["combinational_area_um2"]:.9f} μm² |',
        f'| 时序逻辑面积 | {area["sequential_area_um2"]:.9f} μm² |',
        f'| SRAM 面积 | {area["sram_area_um2"]:.9f} μm² |',
        f'| 总面积（含 SRAM） | {area["area_um2"]:.9f} μm² |',
        f'| 估算 Fmax | {timing["estimated_fmax_mhz"]:.9f} MHz |',
        f'| 最低周期 | {timing["minimum_period_ns"]:.9f} ns |',
        f'| 2 ns 时钟约束下 Worst Setup Slack | {timing["worst_setup_slack_ns"]:.9f} ns |', '',
        '负 Slack 表示不满足 2 ns / 500 MHz 约束；以上 Fmax 是课程 ideal clock、no parasitics 模型的 STA 估算。',
        '本次没有重构模块或做参数优化，因此只运行最终评估 opt 模式，没有重复 diagnose 模式。', '',
        '## 工具适配与日志', '',
        'Windows native：Verilator 5.020、Yosys 0.63、ABC、OpenSTA 3.1.0，使用同一课程 ASAP7/FakeRAM 库，工具 SHA256 已与安装清单核对。',
        '原 make build 在 Windows 归档路径处退出 2；随后以斜杠工具路径运行同一生成目录的 Makefile，完成归档和链接，并加入已有 time-zero fallback。官方 build.py 和 sim.cpp 保持原样。不是无适配的一次 make build 成功。',
        '辅助协议测试初试 Icarus 时因前向声明报错，随后使用课程 Verilator；辅助 C++ 编译统一 C++17，并采用斜杠路径解决 Windows 转义。初始失败日志保留。',
        'Verilator 仍有 WIDTH、UNOPTFLAT 等告警。接口桥接部分已另做位级检查，未发现真实组合环路；未据此宣称全 CPU 所有告警消除。', '',
        '## 复现与产物', '',
        '可用以下命令在新的 F 盘目录复现本次全部流程（始终排除 Pi）：', '', '```powershell',
        'python E:/Verilog_cpu/tools/validate_a109_course_readme.py all --out F:/CPU2026CourseRuns/A109_readme_new_run', '```', '',
        '本次每条 make 命令、退出码、开始结束时间和日志哈希在 *.command.json 中；config.mk 保存实际工具与输出路径。', '',
        '- validation.json：总验证清单及所有证据哈希。', '- interface_audit.json / structural.json / protocols.json：接口、结构和协议证据。',
        '- build/sim.exe、build_identity.json：新仿真器及源码身份。', '- tests.json、correctness_*.log、make_perf.log：逐项结果。',
        '- trace.vcd、run.log、waveform_axi.json：官方单程序运行及外部总线检查。',
        '- synth/opt/report.txt、report.json、timing.rpt、area.json、timing.json、constraints.sdc：新综合完整产物。', '']
    report_path = ROOT / 'reports/A109_README_interface_tests_no_pi_2026-10-06.md'
    report_path.write_text('\n'.join(rows), encoding='utf-8')
    print('COMPLETE ' + str(report_path), flush=True)
    print(json.dumps({k:v for k,v in proof.items() if k != 'artifact_sha256'}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'build', 'tests', 'protocols', 'synth', 'structural', 'waveform', 'boundary', 'finalize', 'all'))
    parser.add_argument('--out', type=Path, default=OUT, help='Use a fresh output directory for a new validation')
    arguments = parser.parse_args()
    OUT = arguments.out.resolve()
    if arguments.phase == 'all':
        for phase in ('prepare', 'build', 'protocols', 'structural', 'tests', 'waveform', 'boundary', 'synth', 'finalize'):
            globals()[phase]()
    else:
        globals()[arguments.phase]()
