"""Distribute iterative MDU payload write controls at existing clock edges."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A36_dcache_word_response'
TARGET=BASE/'A37_mdu_local_payload_owners'
EVIDENCE=Path('F:/CPU2026Proofs/ER1_A21_critical_mdu_endpoint_20261005.json')


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    evidence=read(EVIDENCE)
    assert evidence['endpoint_source_module']=='rv32m_mdu_iterative'
    name='rtl/rv32m_mdu_iterative.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=original
    fields=['finishing_magnitude','finishing_negate','finishing_increment','mode_mul','shift_state',
        'operand','operation','result_negative','remainder_negative','divide_zero','signed_overflow',
        'original_a','operation_tag','operation_phys','operation_live','out_value','out_tag','out_phys','out_live']
    for field in fields:
        pattern=r'    reg (?:\[[^\]]+\] )?'+field+r';'
        match=re.search(pattern,text)
        # finishing flags share a declaration in the original module.
        if field in ('finishing_negate','finishing_increment'):
            continue
        assert match,field
        text=once(text,match[0],match[0].replace('    reg ','    wire ',1))
    text=once(text,'    reg finishing_negate,finishing_increment;',
        '    wire finishing_negate,finishing_increment;')
    payload_assignments=[
        '                shift_state <= next_state;\n',
        '                    finishing_magnitude <= result_magnitude;\n',
        '                    finishing_negate <= result_needs_negate;\n',
        '                    finishing_increment <= result_negate_increment;\n',
        '                out_value<=finishing_value;\n',
        '                out_tag<=operation_tag;\n',
        '                out_phys<=operation_phys;\n',
        '                out_live<=operation_live;\n',
        '                mode_mul <= req_is_mul;\n',
        '                shift_state <= req_is_mul ? {33\'b0, req_abs_b} : {33\'b0, req_abs_a};\n',
        '                operand <= req_is_mul ? req_abs_a : req_abs_b;\n',
        '                operation <= req_op_i;\n',
        '                result_negative <= req_a_negative ^ req_b_negative;\n',
        '                remainder_negative <= req_a_negative;\n',
        '                divide_zero <= !req_is_mul && (req_src2_i == 0);\n',
        '                signed_overflow <= req_is_signed_div &&\n                    (req_src1_i == 32\'h80000000) && (req_src2_i == 32\'hffffffff);\n',
        '                original_a <= req_src1_i;\n',
        '                operation_tag <= req_rob_tag_i;\n',
        '                operation_phys <= req_phys_rd_i;\n',
        '                operation_live <= req_target_live_i && req_rob_tag_i[0];\n',
    ]
    for assignment in payload_assignments:text=once(text,assignment,'')
    old_control=original[original.index('    always @(posedge clk_i)'):]
    projected_control=old_control
    for assignment in payload_assignments:projected_control=once(projected_control,assignment,'')
    assert text[text.index('    always @(posedge clk_i)'):]==projected_control
    owners='''    // Preserve the original capture edges and unreset payload lifetime.
    // A late launch enable formerly drove every operation/shift operand
    // state mux. Named word owners distribute write control per16 data bits.
    wire payload_normal=!reset_i && !flush_i;
    wire payload_launch=payload_normal && req_valid_i && req_ready_o;
    wire payload_iterate=payload_normal && busy && !operation_cancel;
    wire payload_finish_capture=payload_iterate && step==6'd31;
    wire payload_publish=payload_normal && finishing && !operation_cancel && out_slot_ready;
    wire [3:0] launch_views,launch_mode_views;
    rv32_frequency_control_tree #(.LEAVES(4)) launch_tree (
        .signal_i(payload_launch),.views_o(launch_views));
    rv32_frequency_control_tree #(.LEAVES(4)) launch_mode_tree (
        .signal_i(req_is_mul),.views_o(launch_mode_views));
    wire [31:0] initial_low,initial_operand;
    generate for(genvar initial_word=0;initial_word<2;initial_word=initial_word+1) begin:g_initial_word
        assign initial_low[initial_word*16 +: 16]=launch_mode_views[initial_word]?
            req_abs_b[initial_word*16 +: 16]:req_abs_a[initial_word*16 +: 16];
        assign initial_operand[initial_word*16 +: 16]=launch_mode_views[2+initial_word]?
            req_abs_a[initial_word*16 +: 16]:req_abs_b[initial_word*16 +: 16];
    end endgenerate
    wire shift_write;
    wire [64:0] shift_next;
    rv32_frequency_event_select #(.WIDTH(65),.EVENTS(2),.PRIORITY(0)) shift_selector (
        .events_i({payload_iterate,launch_views[0]}),
        .values_i({next_state,33'b0,initial_low}),.write_o(shift_write),.value_o(shift_next));
    rv32_frequency_word_bank #(.WIDTH(65)) shift_state_owner (
        .clk_i(clk_i),.write_i(shift_write),.data_i(shift_next),.data_o(shift_state));
    rv32_frequency_word_bank #(.WIDTH(32)) operand_owner (
        .clk_i(clk_i),.write_i(launch_views[1]),.data_i(initial_operand),.data_o(operand));
    rv32_frequency_word_bank #(.WIDTH(32)) original_owner (
        .clk_i(clk_i),.write_i(launch_views[2]),.data_i(req_src1_i),.data_o(original_a));
    localparam integer OPERATION_PAYLOAD_WIDTH=OP_WIDTH+TAG_WIDTH+PHYS_ADDR_WIDTH+6;
    wire [OPERATION_PAYLOAD_WIDTH-1:0] operation_payload;
    assign {mode_mul,operation,result_negative,remainder_negative,divide_zero,signed_overflow,
        operation_tag,operation_phys,operation_live}=operation_payload;
    rv32_frequency_word_bank #(.WIDTH(OPERATION_PAYLOAD_WIDTH)) operation_owner (
        .clk_i(clk_i),.write_i(launch_views[3]),
        .data_i({req_is_mul,req_op_i,req_a_negative^req_b_negative,req_a_negative,
            !req_is_mul && req_src2_i==32'b0,
            req_is_signed_div && req_src1_i==32'h80000000 && req_src2_i==32'hffffffff,
            req_rob_tag_i,req_phys_rd_i,req_target_live_i && req_rob_tag_i[0]}),.data_o(operation_payload));
    rv32_frequency_word_bank #(.WIDTH(34)) finishing_owner (
        .clk_i(clk_i),.write_i(payload_finish_capture),
        .data_i({result_magnitude,result_needs_negate,result_negate_increment}),
        .data_o({finishing_magnitude,finishing_negate,finishing_increment}));
    localparam integer OUTPUT_PAYLOAD_WIDTH=33+TAG_WIDTH+PHYS_ADDR_WIDTH;
    rv32_frequency_word_bank #(.WIDTH(OUTPUT_PAYLOAD_WIDTH)) output_owner (
        .clk_i(clk_i),.write_i(payload_publish),
        .data_i({finishing_value,operation_tag,operation_phys,operation_live}),
        .data_o({out_value,out_tag,out_phys,out_live}));

'''
    text=once(text,'    always @(posedge clk_i) begin',owners+'    always @(posedge clk_i) begin')
    # Original arithmetic, request/response/recovery readiness and the
    # projected phase/counter process are exact parent text.
    comb_start=original.index('    wire [2*RECOVERY_WIDTH-1:0] recovery_views;')
    comb_end=original.index('    always @(posedge clk_i) begin')
    assert text[text.index('    wire [2*RECOVERY_WIDTH-1:0] recovery_views;'):text.index('    // Preserve the original capture edges')]==original[comb_start:comb_end]
    assert text[text.index('    always @(posedge clk_i)'):]==projected_control
    for n in parent['source_sha256']:
        dest=TARGET/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/n,dest)
    (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['enabled_profile']=dict(parent['enabled_profile'],iterative_mdu_local_payload_owners=True,
        iterative_mdu_payload_owner_extra_state_bits=0,iterative_mdu_payload_owner_extra_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Move shared iterative MDU unreset payload capture into named per16-bit write-control word owners; retain original phase/counter, all arithmetic, cancellation, ready/valid and exact capture edges. Bound launch mode fanout without another M stage.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        iterative_mdu_worst_a21_path_endpoint_source_proof_sha256=sha(EVIDENCE),
        iterative_mdu_payload_control_added_ff_bits=0,iterative_mdu_payload_control_added_edges=0,
        iterative_mdu_local_owners_actual_ppa_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_ITERATIVE_MDU_BOUNDED_PAYLOAD_WRITE_OWNERS_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=[name],
        parent_measurement_snapshot_unchanged=True,added_ff_bits=0,added_pipeline_edges=0,
        original_arithmetic_and_handshake_text_exact=True,original_phase_counter_clock_projection_exact=True,
        source_path_evidence_sha256=sha(EVIDENCE),tests_started=False,adopted=False,
        source_arguments=[
            'A21 frozen endpoint attribution identifies the shared iterative MDU clocked process. Late accept/control nets feed many combinational state-update gates; source payload writes were in one large clocked conditional with no named bounded write-control owners.',
            'Every payload remains unreset and captures only under original !reset&&!flush qualification. launch initializes shift65,operand32,original_a32 and mode/op/sign/error/tag/phys/live. Iteration writes shift65, step31 captures magnitude32+negate+increment, finishing&&!cancel&&out_slot_ready captures original output tuple.',
            'Original payload field widths are preserved: operation packet OP_WIDTH+TAG_WIDTH+PHYS_ADDR_WIDTH+6; output33+TAG_WIDTH+PHYS_ADDR_WIDTH; finishing34; shift65; operand32; original32. No added data/control register or pipeline boundary.',
            'Request initialize has priority over iteration in the event selector, matching original last NBA assignment; original busy/finishing readiness makes the events exclusive. Reset/flush payload silence and operation cancel qualifiers preserve original field lifetime.',
            'The phase/counter clocked process equals the original after removing only payload assignments. Original prefix feedback/final correction, request absolute operands, signed/unsigned operations, zero/overflow rules, whole tags, recovery guard, occupied/ready/valid/backpressure remain exact parent text.',
            'Named frequency_word_bank distributes each write into16-bit leaves; launch pre-distribution has four separate owner views, req mode selects four16-bit initial-data chunks. Additional priced control inverters and event mux mapping may change total area; no frequency result is claimed.',
            'Prepared as an independent successor while immutable A36 measures. A36 source/manifest/manager are not edited. No A37 HDL build, lint, simulation, synthesis, STA, CPU/perf or unit tests.',
            'Before adoption, same-source full M corner cases, completion hold, reset/flush, cancellation at issue/iterate/finish/output, retained older work and stale generation behavior need meaningful validation.'
        ])
    write(BASE/'A37_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','added_ff_bits','added_pipeline_edges','tests_started')})


if __name__=='__main__':main()
