"""Census saved official disassembly only; no CPU/EDA execution."""
from collections import Counter
from pathlib import Path
import re
from manage_frozen_baseline_programs import read, sha, write

RUN = Path('F:/CPU2026CourseRuns/ER1_A16R2_tier3_20261005')
OUT = Path('F:/CPU2026Proofs/ER1_official_perf_static_instruction_mix_20261005.json')
M_OPS = {'mul','mulh','mulhsu','mulhu','div','divu','rem','remu'}


def main():
    assert not OUT.exists()
    manifest = read(RUN/'source_manifest.json')
    testcase_root = RUN/'source/.deps/RISC-V-CPU-2026/testcases'
    rows = []
    for case in sorted(testcase_root.glob('perf_*')):
        if not case.is_dir():
            continue
        program = case/'program.S'
        relative = program.relative_to(RUN/'source').as_posix()
        assert sha(program) == manifest['snapshot_sha256'][relative], relative
        section = None
        sections = set()
        counts = Counter()
        m_instructions = []
        for line in program.read_text(encoding='utf-8').splitlines():
            header = re.fullmatch(r'Disassembly of section (\S+):',line)
            if header:
                section = header[1]
                sections.add(section)
                continue
            instruction = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)',line)
            if not instruction or not section or not section.startswith('.text'):
                continue
            pc, word, mnemonic, operands = instruction.groups()
            assert mnemonic != '.word', (case.name,line)
            opcode = int(word,16)
            encoded_m = (opcode & 0x7f) == 0x33 and (opcode >> 25) == 1
            assert encoded_m == (mnemonic in M_OPS), line
            counts[mnemonic] += 1
            if encoded_m:
                m_instructions.append(dict(pc=int(pc,16),word=word,op=mnemonic,operands=operands))
        assert counts and '.text' in sections
        rows.append(dict(name=case.name, disassembly_sha256=sha(program),
            program_data_sha256=sha(case/'program.data'), metrics_sha256=sha(case/'metrics.json'),
            static_text_instructions=sum(counts.values()),static_m_instructions=len(m_instructions),
            opcode_counts=dict(counts),m_instructions=m_instructions,sections=sorted(sections)))
    assert len(rows) == 6
    result = dict(status='SAVED_OFFICIAL_PERF_DISASSEMBLY_CENSUS',
        source_manifest_sha256=sha(RUN/'source_manifest.json'),results=rows,
        all_six_texts_have_no_m_instructions=all(row['static_m_instructions']==0 for row in rows),
        interpretation='Static linked text only. Not dynamic profiling or proof of control-flow confinement; cannot replace official IPC/correctness measurement.',
        new_cpu_execution=False,new_synthesis=False,new_sta=False)
    write(OUT,result)
    print(dict(status=result['status'],cases=[{k:r[k] for k in ('name','static_text_instructions','static_m_instructions')} for r in rows],
        all_six_texts_have_no_m_instructions=result['all_six_texts_have_no_m_instructions']))


if __name__ == '__main__':
    main()
