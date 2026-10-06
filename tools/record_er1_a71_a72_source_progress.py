"""Bind new source changes, A69 partial PPA and static capacity evidence."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a69_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT / 'build/cpu2026/er1_a69_partial_ppa_a71_a72_source_progress_20261006.json'


def program_capacity_evidence():
    reference = Path('F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005')
    rows = []
    for measured in read(reference / 'result/ipc.json')['results']:
        case = reference / 'source/.deps/RISC-V-CPU-2026/testcases' / measured['name']
        assert sha(case / 'program.data') == measured['program_sha256']
        image = {}
        position = 0
        for line in (case / 'program.data').read_text(encoding='utf-8').splitlines():
            for token in line.split('#', 1)[0].split():
                if token.startswith('@'):
                    position = int(token[1:], 16)
                else:
                    image[position] = int(token, 16)
                    position += 1
        writers = set()
        count = 0
        for line in (case / 'program.S').read_text(encoding='utf-8').splitlines():
            match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+', line)
            if not match:
                continue
            address, word = int(match[1], 16), int(match[2], 16)
            assert word == sum(image[address + byte] << (8 * byte) for byte in range(4)), address
            opcode, rd = word & 127, (word >> 7) & 31
            assert opcode in [0x03, 0x13, 0x17, 0x23, 0x33, 0x37, 0x63, 0x67, 0x6f]
            if opcode in [0x03, 0x13, 0x17, 0x33, 0x37, 0x67, 0x6f] and rd:
                writers.add(rd)
            count += 1
        rows.append(dict(case=measured['name'], program_sha256=sha(case / 'program.data'),
            disassembly_sha256=sha(case / 'program.S'), image_bound_code_words=count,
            statically_written_nonzero_arch_names=sorted(writers), arch_name_count=len(writers),
            conservative_nonzero_map_capacity=55 - len(writers), rob_capacity=32,
            physical_capacity_can_precede_rob_for_legal_text=len(writers) > 23))
    assert sum(row['image_bound_code_words'] for row in rows) == 925
    return dict(rows=rows, reset_fact='All RAT names reset to physical0; initial logical free_count=PHYS_REGS-1=55.',
        capacity_argument='With A live distinct nonzero architectural mappings and W unretired destination allocations, logical free>=55-A-W. At most one destination allocation per ROB row. Static legal-text written-name bounds exceed23 only for rsort; this does not count actual dynamic occupancy, timing, free-pool refill lag or speculative execution outside disassembled legal text.',
        decision='No PRF expansion candidate: capacity alone gives weak aggregate gain evidence, especially for median/qsort/towers/multiply/vvadd. Need dynamic physical-pressure evidence before spending area.',
        new_execution=False)


def main():
    assert not PROOF.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A70_recovery_rob_credit'
    assert state['active_measurement_candidate'] == 'A69_same_edge_redirect_fetch'
    plan = check()
    dispatch = read(RUN / 'dispatch_identity.json')
    assert dispatch['process_id'] == state['measurement_process_id'] == 44708
    assert sha(RUN / 'dispatch_identity.json') == state['measurement_dispatch_sha256']
    alive = live(dispatch['process_id'])
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    active = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous)['main_active_manifest_sha256']
    main = read(active)
    for file, digest in main['source_sha256'].items():
        assert sha(ROOT / file) == digest, file
    candidates = []
    for name, script, digest in [
        ('A71_lsq_second_report_reclaim', 'prepare_er1_lsq_second_report_reclaim.py', '38deccc3af9e3d96044d63b27256a4328e7f7bc1a5a4823abd36e7b479f8f22d'),
        ('A72_branch_capture_redirect_ready', 'prepare_er1_branch_capture_redirect_ready.py', '7371c5f383b1f5c1e884ce7ec480bc741a34746431b4332a18cbd42de55f0bd2'),
    ]:
        root = BASE / name
        manifest = read(root / 'candidate.json')
        assert sha(root / 'candidate.json') == digest
        assert sha(Path(manifest['parent_candidate']) / 'candidate.json') == manifest['parent_candidate_sha256']
        assert sha(ROOT / 'tools' / script) == manifest['preparation_script_sha256']
        for file, expected in manifest['source_sha256'].items():
            assert sha(root / file) == expected, file
        review = BASE / (name.split('_', 1)[0] + '_source_review.json')
        assert read(review)['candidate_sha256'] == digest
        candidates.append(dict(candidate=name, source_root=str(root), candidate_sha256=digest,
            parent_candidate_sha256=manifest['parent_candidate_sha256'], source_file_count=len(manifest['source_sha256']),
            source_hashes_valid=True, preparation_script_sha256=sha(ROOT / 'tools' / script),
            review=str(review), review_sha256=sha(review), changed_files=manifest['changed_from_parent_files'],
            tests_started=False, adopted=False))
    timing_file = RUN / 'result/timing_only.json'
    timing = read(timing_file)
    report = RUN / 'result/synth/opt/report.json'
    critical = RUN / 'result/synth/opt/critical_paths.json'
    assert timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert timing['config_sha256'] == plan['config_sha256']
    assert sha(report) == timing['official_report_sha256']
    paths = []
    fragments = ['branch_capture_owner.data_o', 'out_cancel_guard', 'completion.g_direct_payload',
        'g_producer_live_read[2]', 'response_read.g_event', 'bank_training_index', 'ras_return_address_selector']
    for path in read(critical)['checks']:
        anchors = []
        seen = set()
        for node in path['source_path']:
            net = node.get('net', '')
            if '/' not in net and not net.endswith(('signal_i', 'signal_o')) and any(fragment in net for fragment in fragments) and net not in seen:
                anchors.append(dict(net=net, arrival_ns=node['arrival']*1e9))
                seen.add(net)
        paths.append(dict(startpoint=path['startpoint'], endpoint=path['endpoint'],
            data_arrival_ns=path['data_arrival_time']*1e9, required_ns=path['required_time']*1e9,
            slack_ns=path['slack']*1e9, anchors=anchors))
    ppa = dict(candidate='A69_same_edge_redirect_fetch', run=str(RUN),
        source_manifest_sha256=plan['source_manifest_sha256'], config_sha256=plan['config_sha256'],
        timing_only_sha256=sha(timing_file), ppa_sha256=sha(report), critical_paths_sha256=sha(critical),
        fmax_mhz=timing['fmax_mhz'], area_um2=timing['area_um2'], minimum_period_ns=timing['minimum_period_ns'],
        ipc=None, ipc_still_unknown=True, frequency_goal_failed=True, paths=paths)
    classification = 'PROGRESS_A69_MEASURED_TIMING_REGRESSION_DIAGNOSED_A71_A72_SOURCE_FROZEN_NO_NEW_JOB'
    proof = dict(status='A69_PARTIAL_PPA_A71_A72_INDEPENDENT_SOURCE_PROGRESS',
        recorded_at=datetime.now(timezone.utc).isoformat(), this_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        measured_a69_partial_timing=ppa, pending_candidates=candidates,
        pending_candidate_metrics=dict(ipc=None, fmax_mhz=None, area_um2=None),
        source_cost=dict(new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0),
        static_program_capacity_evidence=program_capacity_evidence(),
        original_process_id=dispatch['process_id'], original_process_live_now=alive,
        active_phase=read(RUN / 'serial_phase_identity.json')['status'],
        new_hdl_or_lint_or_simulation_or_synthesis_or_sta_or_unit_job_started=False,
        measured_incumbent=state['best_measured_combined_result'],
        main_eu_source_unchanged=True, main_active_manifest_sha256=sha(active),
        main_source_file_count=len(main['source_sha256']), adopted=False, goal_complete=False)
    write(PROOF, proof)
    last = candidates[-1]
    state.update(status='A69_TIMING_BELOW_TARGET_IPC_IN_PROGRESS_A72_SOURCE_PENDING_UNTESTED',
        current_prepared_candidate=last['candidate'], current_source_candidate=last['candidate'],
        pending_source_candidate=last['source_root'], pending_source_candidate_sha256=last['candidate_sha256'],
        candidate_manifest_sha256=last['candidate_sha256'], candidate_tests_started=False,
        pending_source_candidate_tests_started=False, candidate_ipc=None, candidate_fmax_mhz=None,
        candidate_area_um2=None, candidate_metrics_belong_to=last['candidate'],
        candidate_correctness_passed=None, candidate_correctness_failed=None,
        candidate_correctness_finished=False, candidate_correctness_not_run=True,
        goal_complete=False, candidates_adopted=False, measurement_process_alive=alive,
        measurement_partial_timing=ppa, measurement_partial_proof=str(PROOF), measurement_partial_proof_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'], last_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF), last_background_progress_sha256=sha(PROOF),
        next_work=['Observe original A69 performance build and official cases without restarting.',
            'Continue removing measured recovery-to-frontend paths while preserving IPC opportunities.',
            'Review remaining source ideas and report before any next coherent native measurement.',
            'Keep measured/pending sources separate; no adoption before numeric goal and complete required functionality coverage.'])
    write(STATE, state)
    print(dict(status=proof['status'], pending_candidate=last['candidate'], proof=str(PROOF), proof_sha256=sha(PROOF),
        original_pid=dispatch['process_id'], original_pid_live_now=alive, new_tests_started=False,
        a69_partial_fmax_mhz=ppa['fmax_mhz'], a69_partial_area_um2=ppa['area_um2']))


if __name__ == '__main__':
    main()
