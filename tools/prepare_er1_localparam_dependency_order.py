"""Order new parameter dependencies before Yosys width/elaboration users."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A93_fast_store_wb_data'
TARGET = BASE/'A94_localparam_dependency_order'
REVIEW = BASE/'A94_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '13e00d4587ba34f677e9c328becc90802973c31eca1616350fcfec7fcb92f67b'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    start = '    localparam integer HEAD_STORE_ACK_ACTIVE='
    end = '    localparam integer HEAD_PACKET_META_WIDTH='
    block = original[original.index(start):original.index(end)]
    text = once(original,block,'')
    marker = '    localparam integer REPORT_IDENTITY_WIDTH='
    text = once(text,marker,block+marker)
    assert text.index('HEAD_STORE_ACK_ACTIVE=') < text.index('HEAD_LOAD_IDENTITY_ACTIVE=')
    assert text.index('HEAD_LOAD_IDENTITY_ACTIVE=') < text.index('HEAD_LOAD_PACKET_ACTIVE=')
    assert text.index('HEAD_LOAD_PACKET_ACTIVE=') < text.index('REPORT_IDENTITY_WIDTH=')
    changes[name] = text
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    block = '''    localparam integer PARALLEL_STORE_ADDRESS=(STORE_ALLOC_EARLY_ADDRESS==2) &&
        (STORE_ALLOC_IMM12!=0) && (PRF_READ_MUX_IMPL!=0);
'''
    text = once(original,block,'')
    marker = '    localparam integer FAST_STORE_COMPLETE_ACTIVE='
    text = once(text,marker,block+marker)
    assert text.index('PARALLEL_STORE_ADDRESS=') < text.index('FAST_STORE_SAVED_ACTIVE=')
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LOCALPARAM_DEPENDENCY_ORDER_REPAIR_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Repair A92 native Yosys width-elaboration failure by declaring new head report constants before REPORT_IDENTITY_WIDTH/SAVED_IDENTITY_QUERY_LSB. Also declare PARALLEL_STORE_ADDRESS before new FAST_STORE_SAVED_ACTIVE constant use. Only existing complete declarations move; no parameter values, boolean expressions, state, ports or behavior are changed.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a92_yosys_frontend_parameter_width_failure_repaired_in_new_source=True,
        localparam_dependency_order_limit='A92 original serial timing rc1: rv32_lsq.v:1215 Failed to detect width for HEAD_LOAD_PACKET_ACTIVE. New A91 constant was used before declaration in a width expression; same forward dependency found in A87 FAST_STORE_SAVED_ACTIVE. Move declarations only. No additional timing gain or successful compilation is claimed before next coherent course run.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Original A92 PID97984 is terminal SERIAL_TIMING_FAILED rc1 with explicit native Yosys diagnostic at frozen LSQ line1215: cannot detect HEAD_LOAD_PACKET_ACTIVE width. No PPA/IPC result exists. A91 used that constant in REPORT_IDENTITY_WIDTH before declaring its dependency chain. This is a new-source declaration ordering error, not measured frequency regression or tool/library version mismatch.',
            'Move unchanged HEAD_STORE_ACK_ACTIVE -> HEAD_LOAD_IDENTITY_ACTIVE -> HEAD_LOAD_PACKET_ACTIVE block before REPORT_IDENTITY_WIDTH/SAVED_IDENTITY_QUERY_LSB. Scan other new constant dependencies and move unchanged PARALLEL_STORE_ADDRESS before FAST_STORE_COMPLETE_ACTIVE/FAST_STORE_SAVED_ACTIVE, since its prior position was also after new constant use. Every expression/value, packet bit field, active/fallback rule and state/port/handshake remains unchanged.',
            'No HDL/lint/formal/simulation/synthesis/STA/unit test run for this repair; frozen A92 is not edited or restarted. A93 data-WB coverage is inherited, unmeasured. Future new coherent run must first be reported, use original successful A83 as tool/dependency reference and retain failed A92 artifacts. Full numerical/ISA/parameter correctness goal remains unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
