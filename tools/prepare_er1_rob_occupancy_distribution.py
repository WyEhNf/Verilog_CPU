"""Distribute the real ROB count to bounded recovery consumers, without state."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A108_head_report_word_select'
TARGET = BASE/'A109_rob_occupancy_distribution'
REVIEW = BASE/'A109_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json') == '0cd768b0c4f9905b39d556e03751842fd98169f89c3771cb95b7745fd45eaa11'
    parent = read(PARENT/'candidate.json')
    assert not parent['tests_started'] and not parent['adopted']
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    files = ['rtl/backend/rv32_rob.v', 'rtl/backend/rv32_backend_joint.v', 'rtl/cpu_core.v', 'rtl/course/student_top.v']
    originals = {n:(PARENT/n).read_text(encoding='utf-8') for n in files}
    texts = dict(originals)
    for name in files[1:]:
        old = '    parameter integer ROB_RECOVERY_ROW_LIVE_QUALIFY = 0,'
        default = 1 if name.endswith('student_top.v') else 0
        texts[name] = once(texts[name], old, old+f'\n    parameter integer ROB_OCCUPANCY_DISTRIBUTE = {default},')
        if name == files[1]:
            old = '.RECOVERY_ROW_LIVE_QUALIFY(ROB_RECOVERY_ROW_LIVE_QUALIFY),'
            texts[name] = once(texts[name], old, old+' .OCCUPANCY_DISTRIBUTE(ROB_OCCUPANCY_DISTRIBUTE),')
        else:
            old = '.ROB_RECOVERY_ROW_LIVE_QUALIFY(ROB_RECOVERY_ROW_LIVE_QUALIFY),'
            texts[name] = once(texts[name], old, old+' .ROB_OCCUPANCY_DISTRIBUTE(ROB_OCCUPANCY_DISTRIBUTE),')
    name = files[0]
    old = '    parameter integer RECOVERY_ROW_LIVE_QUALIFY = 0,'
    texts[name] = once(texts[name], old, old+'\n    parameter integer OCCUPANCY_DISTRIBUTE = 0,')
    old = '    reg [COUNT_WIDTH-1:0] occupancy_reg;'
    texts[name] = once(texts[name], old, old+'''
    // The count remains this one original state owner. Isolate its row
    // recovery comparators and three separate public/query/lane consumers.
    localparam integer OCCUPANCY_ROW_DOMAINS=(ROB_ENTRIES+3)/4;
    localparam integer OCCUPANCY_DOMAINS=OCCUPANCY_ROW_DOMAINS+3;
    wire [OCCUPANCY_DOMAINS*COUNT_WIDTH-1:0] occupancy_views;
    generate if(OCCUPANCY_DISTRIBUTE!=0) begin:g_occupancy_domains
        rv32_frequency_control_tree #(.WIDTH(COUNT_WIDTH),.LEAVES(OCCUPANCY_DOMAINS)) tree (
            .signal_i(occupancy_reg),.views_o(occupancy_views));
    end else begin:g_occupancy_direct
        assign occupancy_views={OCCUPANCY_DOMAINS{occupancy_reg}};
    end endgenerate''')
    texts[name] = once(texts[name],
        'COUNT_WIDTH\'(chosen_age),occupancy_reg}),',
        'COUNT_WIDTH\'(chosen_age),occupancy_views[(OCCUPANCY_ROW_DOMAINS+2)*COUNT_WIDTH +: COUNT_WIDTH]}),')
    texts[name] = once(texts[name], '    assign occupancy_o = occupancy_reg;',
        '    assign occupancy_o = occupancy_views[(OCCUPANCY_ROW_DOMAINS+1)*COUNT_WIDTH +: COUNT_WIDTH];')
    texts[name] = once(texts[name], '(age < occupancy_reg) && (!recovery_found || age < chosen_age)',
        '(age < occupancy_views[OCCUPANCY_ROW_DOMAINS*COUNT_WIDTH +: COUNT_WIDTH]) && (!recovery_found || age < chosen_age)')
    texts[name] = once(texts[name], 'row_age<occupancy_reg',
        'row_age<occupancy_views[(command_row/4)*COUNT_WIDTH +: COUNT_WIDTH]')
    texts[name] = once(texts[name], '(bank_younger_age < occupancy_reg)',
        '(bank_younger_age < occupancy_views[(bank_reset_slot/4)*COUNT_WIDTH +: COUNT_WIDTH])')
    texts[name] = once(texts[name], '(younger_age < occupancy_reg)',
        '(younger_age < occupancy_views[(reset_slot/4)*COUNT_WIDTH +: COUNT_WIDTH])')
    assert [l for l in texts[name].splitlines() if 'occupancy_reg <=' in l] == [l for l in originals[name].splitlines() if 'occupancy_reg <=' in l]
    for name in parent['source_sha256']:
        dest = TARGET/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, dest)
    for name, content in texts.items():
        (TARGET/name).write_text(content, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_REAL_ROB_COUNT_BOUNDED_RECOVERY_CONSUMERS_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(), source_root=str(TARGET), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'), changed_from_parent_files=files,
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], ROB_OCCUPANCY_DISTRIBUTE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], ROB_OCCUPANCY_DISTRIBUTE=1,
        rob_occupancy_one_state_owner_retained=True, rob_occupancy_rows_per_domain=4,
        rob_occupancy_distribute_added_ff_bits=0, rob_occupancy_distribute_added_sram_bits=0,
        rob_occupancy_distribute_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Use priced original control tree for real ROB occupancy count, one domain per4 recovery rows plus lane qualification/public output/descriptor query domains. Replace only rawcount consumer wiring, retaining original COUNT_WIDTH, unsigned comparisons, full binary count/slot behavior, original state and allocation/commit/recovery equations. Default0 directviews equal old count; course1 adds combinational drivers, no duplicated FF or new clock latency. A105 mapped root occupancy bit3 FF had33.77fF,177.6ps TCQ and170.6ps inverter delay.'
    ]
    write(TARGET/'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'], changed_files=files, tests_started=False,
        new_declared_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        occupancy_state_assignments_unchanged=True,
        source_arguments=[
            'Original functional frequency tree makes every COUNT_WIDTH-bit view exactly occupancy_reg, same pre-edge bits and original unsigned type. Every modified comparison replaces only its RHS with a same-width equal wire; chosen age/slot priority, rowkill/valid/GEN/recovery mask and public occupancy are identical for all binary states. Existing command_row/genvar and bank_reset_slot/reset_slot static loop rows use floor(row/4), always within ceil(ROB_ENTRIES/4), including entries1/nonpower/partial lastdomain. No modulo or count width change.',
            'Count remains the one original occupancy_reg, with original reset<=0, recovery<=branch_age+1 and normal<=occupancy_reg-pop+allocation assignments byte-identical. Free_entries arithmetic, commit/alloc/fire/clock-edge behavior and scarce-resource conservation are untouched. Tree carries values only, not derived acceptance; it cannot invent credit or form ready/valid feedback. mode0 wires replicate exact count without added drivers, core/backend default0, course1.',
            'The original A105 path starts from FF_396008_. Netlist source mapping execution_recovery_tree.signal_i bit13 is original countbit3 (W5 ages+W5 head+6count+apply). Matching mapped INV output to original designJSON bit10280 and its driver FF QN10279 binds the launch to one original real count state, not a branch result or new duplicated state. Original FF QN load33.77fF,TCQ177.6ps, followingINV170.6ps make348.2ps before recovery qualification. ROB source still fed per-row occupancy comparisons directly despite other descriptor trees. Separate those loads and public/query branches with small combinational domains.',
            'Actual total delay/area is unknown: drivers add latency/cells, public backend leaf can still have high load, and mapping may move the bottleneck. Together A108 targets the late report73bit mux and restores original9bit ROB live query; A106/A107 target prior recovery/admission serialchains without changing cycle behavior. No promise300MHz/IPC1.1 or<=36000 before actual coherent measurement. No new HDL/lint/formal/sim/synthesis/STA/unit tests or CPU builds. Full goal remains unadopted/incomplete.'
        ], candidate_metrics=None, goal_complete=False, adopted=False)
    write(REVIEW, proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
