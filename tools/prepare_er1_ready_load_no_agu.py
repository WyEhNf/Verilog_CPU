"""Prepare source-only removal of redundant AGU work for ready-base loads."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A5_narrow_rob_packets'
TARGET = BASE / 'A6_ready_load_no_agu'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists(), TARGET
    pm = read(PARENT / 'candidate.json')
    for name, digest in pm['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_backend_joint.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer EARLY_LOAD_ADDRESS = 0,',
        '''    // 0: ordinary AGU; 1: allocate ready address and retain AGU;
    // 2 or above: skip redundant RS/AGU work only for a qualified ready load.
    parameter integer EARLY_LOAD_ADDRESS = 0,''')
    text = once(text, '    assign rs_alloc_valid = d_valid;',
        '''    // The same predicate that writes an authoritative LSQ address
    // proves this load needs no later AGU. LSQ remains its sole completion
    // producer. Keep conservative rename/dispatch RS reservations unchanged.
    wire [BE_WIDTH-1:0] load_without_agu = (EARLY_LOAD_ADDRESS>=2) ?
        (d_is_load & ~d_is_store & lsq_alloc_addr_valid) : {BE_WIDTH{1'b0}};
    assign rs_alloc_valid = d_valid & ~load_without_agu;''')
    assert blocks(text) == blocks((PARENT / name).read_text(encoding='utf-8'))
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, 'parameter integer EARLY_LOAD_ADDRESS = 1,',
                'parameter integer EARLY_LOAD_ADDRESS = 2,')
    changes[name] = text
    for name in pm['source_sha256']:
        dest = TARGET / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dest)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(pm)
    record.update(status='PREPARED_UNTESTED_NOT_ADOPTED',source_root=str(TARGET),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        created_at=datetime.now(timezone.utc).isoformat(),
        source_sha256={n:sha(TARGET/n) for n in pm['source_sha256']},
        changed_from_parent_files=list(changes),preparation_script_sha256=sha(Path(__file__)))
    record['parameter_overrides'] = dict(pm['parameter_overrides'],EARLY_LOAD_ADDRESS=2)
    record['implemented_changes'] = list(pm['implemented_changes']) + [
        'Skip redundant RS/AGU allocation only for ready-base loads with a simultaneously allocated LSQ address.'
    ]
    write(TARGET/'candidate.json',record)
    proof = dict(status='SOURCE_REVIEW_ONLY_NOT_FULL_CORE_PROOF',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=list(changes),new_state_bits=0,added_pipeline_cycles=0,
        clocked_blocks_text_equal=True,tests_started=False,adopted=False,
        reasoning=[
            'Elision is gated by the original full allocation-address predicate: enabled adders, valid D lane, load, ready source; stores are explicitly excluded.',
            'Default mode0 and mode1 preserve original RS allocations. A disabled store/address path also disables elision.',
            'Missing-base loads retain original RS/issue/AGU path. All stores, ALU/M-extension/branch operations are unchanged.',
            'Rename reserves an RS slot for every instruction and dispatch keeps counting it. Consuming fewer actual slots preserves capacity safety; it may under-advertise capacity.',
            'ROB allocation, PRF destination mapping, LSQ allocation/tag/address/size/unsigned/phys and map writes remain unchanged.',
            'Ordinary ALU load results were already excluded from completion arbitration; LSQ remains the load result/error producer.',
            'No linked RS owner is installed for elided loads because rs_alloc_fire is zero. Store links are unaffected.',
            'LSQ ordering, forwarding, cache transactions, full-generation completion qualification and in-order retirement remain intact.',
            'This removes one RS allocation and one issued AGU for every elided load. Actual eligible share, IPC and timing remain unmeasured.'
        ])
    write(BASE/'A6_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','new_state_bits','tests_started')})


if __name__ == '__main__':
    main()
