"""Assemble and oracle-check finite RV32IM edges, then run frozen real CPU builds.

Course benchmarks, drivers, memory latency, and RTL are never changed. Generated
programs use a 32-bit signature MMIO exit; coverage is not a complete ISA proof.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from rv32im_arch_oracle import execute, REQUIRED_OPS, R_OPS, M_OPS, I_OPS, SPEC_URLS

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / '.deps/riscv-toolchain-install/xpack-riscv-none-elf-gcc-15.2.0-1/bin'


def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def run(command, log):
    result = subprocess.run([str(x) for x in command], text=True, capture_output=True)
    log.write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode: raise RuntimeError(str(log))
    return result


def assemble(name, body, out):
    prefix = out / name
    source, obj, elf, binary = [prefix.with_suffix(s) for s in ('.S', '.o', '.elf', '.bin')]
    source.write_text('.option norvc\n.option norelax\n.section .text\n.globl _start\n_start:\n'
                      + '\n'.join(body) + '\n', encoding='utf-8')
    run([BIN / 'riscv-none-elf-as.exe', '-march=rv32im', '-mabi=ilp32', '-o', obj, source],
        prefix.with_suffix('.as.log'))
    run([BIN / 'riscv-none-elf-ld.exe', '-m', 'elf32lriscv', '--no-relax', '-Ttext=0',
         '-e', '_start', '-o', elf, obj], prefix.with_suffix('.ld.log'))
    run([BIN / 'riscv-none-elf-objcopy.exe', '-O', 'binary', '-j', '.text', elf, binary],
        prefix.with_suffix('.objcopy.log'))
    dis = run([BIN / 'riscv-none-elf-objdump.exe', '-d', '-M', 'no-aliases', elf],
              prefix.with_suffix('.disasm'))
    data = binary.read_bytes()
    if len(data) % 4: raise ValueError('non-RV32 alignment')
    image = prefix.with_suffix('.image')
    image.write_text('@00000000\n' + '\n'.join(' '.join(f'{b:02X}' for b in data[n:n + 16])
                                              for n in range(0, len(data), 16)) + '\n')
    return data, image


def fold(reg):
    return [f'xor x31,x31,x{reg}', 'slli x29,x31,5', 'xor x31,x31,x29', 'addi x31,x31,97']


def finish(body):
    return body + ['lui x30,0x80000', 'sw x31,0(x30)', '1: jal x0,1b']


def start(seed):
    rng = random.Random(seed)
    return [f'li x{r},0x{rng.getrandbits(32):08x}' for r in range(1, 32)]


def arithmetic(part):
    body = start(100 + part)
    values = [0, 1, 2, 31, 32, 63, 0x7fffffff, 0x80000000, 0xffffffff, 0xaaaa5555]
    pairs = [(a, b) for a in values for b in values][part::4]
    for a, b in pairs:
        body += [f'li x26,0x{a:08x}', f'li x27,0x{b:08x}']
        for op in R_OPS + ['sub', 'sra'] + M_OPS:
            body += [f'{op} x3,x26,x27'] + fold(3)
    for a in values:
        body += [f'li x26,0x{a:08x}']
        for op in ['addi', 'slti', 'sltiu', 'xori', 'ori', 'andi']:
            for imm in (-2048, -1, 0, 255, 2047):
                body += [f'{op} x3,x26,{imm}'] + fold(3)
        for op in ('slli', 'srli', 'srai'):
            for amount in (0, 1, 16, 31):
                body += [f'{op} x3,x26,{amount}'] + fold(3)
    # Writes to x0 must be ignored, including long-latency operations.
    for op in R_OPS + ['sub', 'sra'] + M_OPS:
        body += [f'{op} x0,x26,x27', 'addi x3,x0,73'] + fold(3)
    body += ['lui x3,0xfffff'] + fold(3) + ['auipc x3,0x80000'] + fold(3)
    return finish(body)


def memory_case(high):
    base = 0x0ffffe00 if high else 0x10000
    body = start(200 + high) + [f'li x28,{base + 128}']
    for offset in range(-128, 384, 4):
        body += [f'li x3,0x{(offset * 0x1234567 + 0x89abcdef) & 0xffffffff:08x}',
                 f'sw x3,{offset}(x28)']
    for offset in (-128, -4, 0, 12, 16, 124, 252, 380):
        for lane in range(4):
            body += ['li x3,0xffff8081', f'sb x3,{offset + lane}(x28)',
                     f'lb x4,{offset + lane}(x28)'] + fold(4)
            body += [f'lbu x5,{offset + lane}(x28)'] + fold(5)
        for lane in (0, 2):
            body += ['li x3,0x8001', f'sh x3,{offset + lane}(x28)',
                     f'lh x4,{offset + lane}(x28)'] + fold(4)
            body += [f'lhu x5,{offset + lane}(x28)'] + fold(5)
        body += [f'lw x6,{offset}(x28)'] + fold(6)
        body += [f'lw x0,{offset}(x28)', 'addi x6,x0,1'] + fold(6)
    # Address depends on a divide; overlapping younger loads must wait/forward.
    body += ['li x1,252', 'li x2,3', 'div x3,x1,x2', 'add x3,x28,x3',
             'li x4,0x8badf00d', 'sw x4,0(x3)', 'sb x4,85(x28)',
             'lh x5,84(x28)'] + fold(5) + ['lw x6,0(x3)'] + fold(6)
    for offset in range(-128, 384, 4):
        body += [f'lw x6,{offset}(x28)'] + fold(6)
    return finish(body)


def control_case(padding):
    body = ['addi x0,x0,0'] * padding + start(300 + padding)
    body += ['lui x28,0x10', 'sw x0,0(x28)']
    pairs = [(0, 0), (0, 1), (1, 0), (0x80000000, 1), (0xffffffff, 0x7fffffff)]
    k = 0
    for op in ('beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu'):
        for a, b in pairs:
            body += [f'li x1,{a}', f'li x2,{b}', f'{op} x1,x2,taken_{k}',
                     'addi x31,x31,7', 'sw x1,0(x28)', f'jal x0,end_{k}',
                     f'taken_{k}:', 'addi x31,x31,-29', 'sw x2,0(x28)',
                     f'end_{k}:', 'lw x3,0(x28)'] + fold(3)
            k += 1
    # JALR must use the old source when rd==rs1 and clear only target bit zero.
    body += ['la x7,jalr_target', 'ori x7,x7,1', 'jalr x7,0(x7)',
             'addi x31,x31,99', 'sw x7,0(x28)', 'jalr_target:'] + fold(7)
    body += ['jal x5,forward', 'addi x31,x31,101', 'forward:'] + fold(5)
    body += ['la x6,negative_target', 'addi x6,x6,13', 'jalr x8,-12(x6)',
             'addi x31,x31,103', 'negative_target:'] + fold(8)
    body += ['li x9,37', 'loop:', 'addi x31,x31,3', 'addi x9,x9,-1', 'bne x9,x0,loop']
    return finish(body)


def random_case(seed):
    rng = random.Random(seed)
    body = start(seed) + ['lui x28,0x10']
    for offset in range(0, 256, 4): body += [f'sw x{1 + offset % 24},{offset}(x28)']
    for n in range(360):
        dst, a, b = rng.randint(1, 24), rng.randint(0, 24), rng.randint(0, 24)
        kind = n % 6
        if kind < 2:
            op = rng.choice(R_OPS + ['sub', 'sra'] + M_OPS)
            body += [f'{op} x{dst},x{a},x{b}']
        elif kind == 2:
            op = rng.choice(I_OPS + ['srai'])
            imm = rng.randrange(32) if op in ('slli', 'srli', 'srai') else rng.randrange(-2048, 2048)
            body += [f'{op} x{dst},x{a},{imm}']
        elif kind == 3:
            op, width = rng.choice([('sb', 1), ('sh', 2), ('sw', 4)])
            offset = rng.randrange(256 // width) * width
            body += [f'{op} x{a},{offset}(x28)', f'lw x{dst},{offset & ~3}(x28)']
        elif kind == 4:
            op, width = rng.choice([('lb', 1), ('lbu', 1), ('lh', 2), ('lhu', 2), ('lw', 4)])
            body += [f'{op} x{dst},{rng.randrange(256 // width) * width}(x28)']
        else:
            op = rng.choice(['beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu'])
            body += [f'{op} x{a},x{b},skip_{n}', f'addi x{dst},x{dst},17', f'skip_{n}:']
        body += fold(dst)
    for r in range(1, 25): body += fold(r)
    for offset in range(0, 256, 4): body += [f'lw x25,{offset}(x28)'] + fold(25)
    return finish(body)


def prepare(out):
    if out.exists(): raise ValueError('preserve existing suite')
    out.mkdir(parents=True)
    report = dict(status='PREPARING',specification_sources=SPEC_URLS, cases=[], input_sha256={},
                  scope='Additional finite RV32IM signature tests; not benchmark IPC or complete ISA proof')
    # Constants are independently specified, not computed by the oracle or RTL.
    fixtures = [('div_negative', ['li x1,-7', 'li x2,3', 'div x31,x1,x2'], 0xfffffffe),
                ('rem_negative', ['li x1,-7', 'li x2,3', 'rem x31,x1,x2'], 0xffffffff),
                ('div_zero', ['li x1,17', 'div x31,x1,x0'], 0xffffffff),
                ('rem_zero', ['li x1,0x89abcdef', 'remu x31,x1,x0'], 0x89abcdef),
                ('div_overflow', ['li x1,0x80000000', 'li x2,-1', 'div x31,x1,x2'], 0x80000000),
                ('rem_overflow', ['li x1,0x80000000', 'li x2,-1', 'rem x31,x1,x2'], 0),
                ('mulhsu_sign', ['li x1,-2', 'li x2,-1', 'mulhsu x31,x1,x2'], 0xfffffffe),
                ('mulhu_high', ['li x1,-1', 'mulhu x31,x1,x1'], 0xfffffffe),
                ('shift_mask', ['li x1,0x80000000', 'li x2,63', 'sra x31,x1,x2'], 0xffffffff),
                ('sltiu_sign', ['li x1,0x80000000', 'sltiu x31,x1,-1'], 1),
                ('byte_sign', ['lui x1,0x10', 'li x2,128', 'sb x2,3(x1)', 'lb x31,3(x1)'], 0xffffff80),
                ('byte_zero', ['lui x1,0x10', 'li x2,128', 'sb x2,3(x1)', 'lbu x31,3(x1)'], 128),
                ('half_sign', ['lui x1,0x10', 'li x2,0x8001', 'sh x2,2(x1)', 'lh x31,2(x1)'], 0xffff8001),
                ('half_zero', ['lui x1,0x10', 'li x2,0x8001', 'sh x2,2(x1)', 'lhu x31,2(x1)'], 32769),
                ('x0_discard', ['li x0,17', 'addi x31,x0,9'], 9),
                ('auipc_pc', ['addi x0,x0,0', 'auipc x31,0'], 4),
                ('jal_link', ['jal x31,there', 'addi x31,x0,99', 'there:'], 4),
                ('jalr_old_source', ['addi x7,x0,13', 'jalr x7,0(x7)', 'addi x7,x0,99', 'addi x31,x7,0'], 8)]
    fixture_results = []
    for name, body, expected in fixtures:
        code, image = assemble('fixture_' + name, finish(body), out)
        oracle = execute(code)
        if oracle['expected_u32'] != expected: raise AssertionError((name, oracle, expected))
        fixture_results.append(dict(name=name, expected_u32=expected, status='PASS'))
    # Invalid generator output must fail, rather than silently establish an answer.
    rejected = 0
    for name, body in [('uninitialized_register', ['add x31,x1,x0']),
                       ('uninitialized_memory', ['lui x1,0x10', 'lw x31,0(x1)']),
                       ('unaligned_load', ['lui x1,0x10', 'lw x31,1(x1)']),
                       ('omitted_system', ['ecall'])]:
        code, _ = assemble('reject_' + name, finish(body), out)
        try: execute(code)
        except (ValueError, KeyError): rejected += 1
        else: raise AssertionError('oracle accepted ' + name)
    report.update(oracle_known_answer_fixtures=fixture_results, rejected_invalid_fixtures=rejected)
    bodies = [(f'arithmetic_edges_{n}', arithmetic(n)) for n in range(4)]
    bodies += [('memory_low', memory_case(False)), ('memory_ram_top', memory_case(True))]
    bodies += [(f'control_alignment_{n}', control_case(n)) for n in (0, 7)]
    bodies += [(f'random_seed_{n}', random_case(n)) for n in range(8)]
    coverage, events = Counter(), Counter()
    for name, body in bodies:
        code, image = assemble(name, body, out)
        oracle = execute(code)
        coverage.update(oracle['coverage']); events.update(oracle['events'])
        report['cases'].append(dict(name=name, image=str(image), **oracle))
        print('PREPARED ' + name, flush=True)
    if set(coverage) != REQUIRED_OPS: raise AssertionError(sorted(REQUIRED_OPS - set(coverage)))
    for op in ('beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu'):
        assert events[op + '_taken'] and events[op + '_not_taken']
    assert events['division_by_zero'] and events['signed_division_overflow']
    assert events['jalr_low_bit_cleared'] and events['jalr_rd_equals_rs1']
    for path in sorted(out.iterdir()):
        if path.is_file(): report['input_sha256'][str(path)] = sha(path)
    for path in [Path(__file__), ROOT / 'tools/rv32im_arch_oracle.py'] + [
        BIN / f'riscv-none-elf-{tool}.exe' for tool in ('as', 'ld', 'objcopy', 'objdump')]:
        report['input_sha256'][str(path)] = sha(path)
    report.update(status='COMPLETE', coverage=dict(coverage), events=dict(events), instruction_types=len(coverage))
    write_json(out / 'suite.json', report)
    print(f'COMPLETE{len(bodies)} prepared programs, {len(coverage)} executed RV32IM instruction types', flush=True)


def native(args):
    out, source = args.outdir.resolve(), args.source_root.resolve()
    if out.exists(): raise ValueError('preserve existing native evidence')
    suite_path = args.suite.resolve() / 'suite.json'
    suite = json.loads(suite_path.read_text(encoding='utf-8-sig'))
    assert suite['status'] == 'COMPLETE' and suite['instruction_types'] == 45
    hashes = dict(suite['input_sha256'])
    hashes[str(suite_path)] = sha(suite_path)
    manifest_path = args.build.resolve() / 'build_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    hashes[str(manifest_path)] = sha(manifest_path)
    for path, value in manifest['source_sha256'].items(): hashes[str(source / path)] = value.lower()
    exe, driver = Path(manifest['executable']), Path(manifest['generated_driver'])
    hashes[str(exe)] = manifest['executable_sha256'].lower()
    hashes[str(driver)] = manifest['generated_driver_sha256'].lower()
    original = source / '.deps/RISC-V-CPU-2026/scripts/sim.cpp'
    observation = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
    observed = driver.read_text()
    assert observed.count(observation) == 1 and observed.replace(observation, '') == original.read_text()
    hashes[str(original)] = sha(original)
    for path, value in hashes.items(): assert sha(path) == value, path
    out.mkdir(parents=True)
    report = dict(status='RUNNING', input_sha256=hashes, results=[], source_root=str(source),
                  parameter_overrides=manifest['parameter_overrides'], memory_latency=20,
                  scope=suite['scope'], oracle='independent sequential decoder of GNU assembled bytes',
                  driver='original course sim.cpp plus read-only retirement print',
                  exit='MMIO0x80000000 word WSTRBf Bhandshake')
    for case in suite['cases']:
        name, expected = case['name'], case['expected_u32']
        log = out / (name + '.log')
        result = subprocess.run([str(exe), case['image'], str(expected), '200000', '20'],
                                cwd=source, text=True, capture_output=True)
        log.write_text(result.stdout + result.stderr, encoding='utf-8')
        hashes[str(log)] = sha(log)
        match = re.search(r'^PASS cycles=(\d+) result=(\d+) expected=(\d+)$', result.stdout, re.M)
        retired = re.search(r'^CPU2026 instret=(\d+)$', result.stderr, re.M)
        passed = result.returncode == 0 and match and retired and int(match[2]) == int(match[3]) == expected
        entry = dict(name=name, status='PASS' if passed else 'FAIL', expected_u32=expected,
                     oracle_instructions_through_exit_store=case['instructions_through_exit_store'], log=str(log))
        if passed: entry.update(cycles=int(match[1]), native_instret=int(retired[1]))
        report['results'].append(entry)
        write_json(out / 'report.json', report)
        print(entry['status'] + ' ' + name, flush=True)
        if not passed:
            report.update(status='FAILED', failure_log=str(log)); write_json(out / 'report.json', report)
            raise SystemExit(str(log))
    for path, value in hashes.items(): assert sha(path) == value, path
    report.update(status='COMPLETE', instruction_types=suite['instruction_types'], coverage=suite['coverage'],
                  events=suite['events'], all_input_hashes_rechecked=True)
    write_json(out / 'report.json', report)
    print(f'COMPLETE{len(report["results"])} additional native RV32IM cases', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--suite', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--outdir', type=Path)
    args = parser.parse_args()
    if args.prepare: prepare(args.prepare.resolve())
    else:
        if not all((args.suite, args.build, args.source_root, args.outdir)): parser.error('native paths required')
        native(args)


if __name__ == '__main__': main()
