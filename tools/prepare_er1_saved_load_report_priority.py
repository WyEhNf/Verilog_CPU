"""Keep current head response outside the saved-report priority network."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A87_saved_store_operands_parallel_admission'
TARGET = BASE/'A88_saved_load_report_priority'
REVIEW = BASE/'A88_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '2b4c3d7b32192462f54273afff9f698cfa28873004ab7021e3a7c55c86e2826c'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer LOAD_COMPLETION_BYPASS = 0,'
    text = once(original, marker, marker+'\n    parameter integer SAVED_REPORT_PRIORITY = 0,')
    marker = '                assign report_eligible[report_row]=report_valid_tree[REPORT_ROWS+report_row];'
    text = once(text, marker, '''                if(SAVED_REPORT_PRIORITY!=0 && LOAD_COMPLETION_BYPASS==2) begin:g_saved_report_eligibility
                    // Head-fast report selection already overrides normal
                    // priority. Keep the late response outside that network.
                    assign report_eligible[report_row]=row_in_report_range &&
                        valid_mem[report_row] && load_mem[report_row] &&
                        complete_mem[report_row] && !load_reported_mem[report_row];
                end else begin:g_original_report_eligibility
                    assign report_eligible[report_row]=report_valid_tree[REPORT_ROWS+report_row];
                end''')
    marker = '    always @* begin\n        complete_slot_found=report_valid_tree[1];'
    assert text[text.index(marker):] == original[original.index(marker):]
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer LOAD_COMPLETION_BYPASS = '+('2' if default else '0')+','
        text = once(original, marker, marker+'\n    parameter integer LSQ_SAVED_REPORT_PRIORITY = '+str(default)+',')
        suffix = '.SAVED_REPORT_PRIORITY(LSQ_SAVED_REPORT_PRIORITY)' if '/backend/' in name else '.LSQ_SAVED_REPORT_PRIORITY(LSQ_SAVED_REPORT_PRIORITY)'
        text = once(text, '.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS)',
            '.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS), '+suffix)
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_SAVED_LOAD_REPORT_PRIORITY_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_SAVED_REPORT_PRIORITY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_SAVED_REPORT_PRIORITY=1,
        saved_load_report_priority_new_ff_bits=0,saved_load_report_priority_new_sram_bits=0,saved_load_report_priority_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'In head-only load completion mode, general report eligibility/age priority uses saved completed rows exclusively. Actual report validity and held-report/head-fast override remain original. This removes current head response from the unused general wrap/prefix priority network without changing the selected valid report or its payload.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        current_head_load_response_removed_from_general_priority=True,
        saved_load_report_priority_limit='Targets A83 actual LSQ return-to-wrap enable1.260ns and later report selection/query1.397/1.597ns. Head-fast and saved report still use final priority selection and full ROB lookup; no extra IPC edge removal or numerical gain claim.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Old general report_eligible contains saved complete OR row_fast_response, so the measured head response also controls global wrap/prefix arbitration before report payload and ROB query. In LOAD_COMPLETION_BYPASS2, fast_head_reports already has strict priority over the general result unless original saved held ownership wins. Its participation in the unused general priority is redundant.',
            'No fast_head_present: all in-range row_fast_response are0, so original and saved-only eligibility/grants equal. Fast head present, no hold: report_first is exclusively the original unique fast-head one-hot and ignores general priority. Fast head present with live hold: original full-tag report_hold_matches wins and also ignores general priority. These cases exhaust the enabled mode; actual public validity and original complete_slot tournament, packet/error/value and metadata acceptance stay byte-identical.',
            'Default0 and arbitrary-row bypass1 use exact old eligibility. No saved flag, capture/pop/count/GEN, report-hold state, response formatting or handshake edge changes; no FF/SRAM/depth is added. Duplicate saved-eligibility gates and changed mapping/fanout may affect area/timing, so a quantified gain is unproven.',
            'Manual source/priority reasoning only; no HDL/lint/formal/simulation/synthesis/STA/unit tests. Future coherent coverage includes simultaneous saved and head returns in both circular halves, held/stalled packet, stale/recycled ownership, reset/flush/recovery, empty/full/wrapped/nonpower-of-two queue, all bypass/default modes, real accepted report/reclaim and full ISA/course performance. All actual full identities and A87 fallback coverage remain required.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
