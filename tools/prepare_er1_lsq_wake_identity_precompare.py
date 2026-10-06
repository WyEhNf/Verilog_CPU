"""Prepare physical wake comparisons before the saved/head report choice."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A109_rob_occupancy_distribution'
TARGET = BASE/'A110_lsq_wake_identity_precompare'
REVIEW = BASE/'A110_source_review.json'
FLAG = 'LSQ_WAKE_IDENTITY_PRECOMPARE'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json') == '2b31e8b8dea04efc2a8680bb38765e55a1d2724bb01f33c7492300eb2cc9e128'
    parent = read(PARENT/'candidate.json')
    assert not parent['adopted']
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    files = ['rtl/backend/rv32_lsq.v','rtl/backend/rv32_reservation_station.v',
        'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']
    originals = {n:(PARENT/n).read_text(encoding='utf-8') for n in files}
    texts = dict(originals)
    for name in files[2:]:
        default = 1 if name.endswith('student_top.v') else 0
        old = f'    parameter integer LSQ_HEAD_LOAD_PACKET_PRESELECT = {default},'
        texts[name] = once(texts[name], old, old+f'\n    parameter integer {FLAG} = {default},')
        if name != files[2]:
            old = '.LSQ_HEAD_LOAD_PACKET_PRESELECT(LSQ_HEAD_LOAD_PACKET_PRESELECT),'
            texts[name] = once(texts[name], old, old+f' .{FLAG}({FLAG}),')
    name = files[0]
    old = '    output wire [2*ROB_TAG_WIDTH-1:0] load_report_identity_tags_o,'
    texts[name] = once(texts[name], old, old+'\n    output wire [2*PHYS_ADDR_WIDTH-1:0] load_report_physical_candidates_o,')
    old = '        // A late head/saved choice must not drive the entire report word.'
    texts[name] = once(texts[name], old, '''        // The same two pre-choice physical destinations feed an optional
        // match-before-choice wake path. Public report packet stays exact.
        assign load_report_physical_candidates_o={
            head_packet_metadata[TAG_WIDTH +: PHYS_ADDR_WIDTH],
            saved_identity_tree[1][ROB_TAG_WIDTH+TAG_WIDTH+33 +: PHYS_ADDR_WIDTH]};
'''+old)
    old = '        assign head_packet_metadata=0;'
    texts[name] = once(texts[name], old, old+'\n        assign load_report_physical_candidates_o=0;')
    marker = '    genvar report_row'
    if marker in originals[name]:
        assert texts[name][texts[name].index(marker):] == originals[name][originals[name].index(marker):]
    name = files[2]
    old = '    wire [2*TAG_WIDTH-1:0] lsq_report_identity_tags;'
    texts[name] = once(texts[name], old, old+'''
    wire [2*PAW-1:0] lsq_report_physical_candidates;
    wire [2*RS_SOURCE_TAG_WIDTH-1:0] lsq_report_wake_candidates;''')
    old = '    wire lsq_report_identity_recovery_kill;'
    texts[name] = once(texts[name], old, '''    localparam integer LSQ_WAKE_IDENTITY_ACTIVE=(LSQ_WAKE_IDENTITY_PRECOMPARE!=0) &&
        LSQ_HEAD_LOAD_IDENTITY_ACTIVE && (LSQ_HEAD_LOAD_PACKET_PRESELECT!=0) &&
        RS_DIRECT_WAKE && (RS_WAKE_MUX_IMPL!=0);
    generate if(LSQ_WAKE_IDENTITY_ACTIVE!=0) begin:g_load_wake_candidates
        for(genvar load_wake_candidate=0;load_wake_candidate<2;load_wake_candidate=load_wake_candidate+1) begin:g_identity
            wire [PAW-1:0] phys=lsq_report_physical_candidates[load_wake_candidate*PAW +: PAW];
            assign lsq_report_wake_candidates[load_wake_candidate*RS_SOURCE_TAG_WIDTH +: RS_SOURCE_TAG_WIDTH]=
                {phys,(phys!=0 && phys<PHYS_REGS)};
        end
    end else begin:g_no_load_wake_candidates
        assign lsq_report_wake_candidates=0;
    end endgenerate
'''+old)
    old = '.load_report_identity_tags_o(lsq_report_identity_tags),'
    texts[name] = once(texts[name], old, old+' .load_report_physical_candidates_o(lsq_report_physical_candidates),')
    old = '.WAKE_UNIQUE_OWNER(RS_DIRECT_WAKE), .WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL),'
    texts[name] = once(texts[name], old, old+' .REPORT_WAKE_PRECOMPARE(LSQ_WAKE_IDENTITY_ACTIVE), .REPORT_WAKE_LANE(LSQ_SOURCE),')
    old = '.wake_valid_i(rs_wake_valid), .wake_tag_i(rs_wake_tag), .wake_value_i(rs_wake_value),'
    texts[name] = once(texts[name], old, old+' .report_wake_tags_i(lsq_report_wake_candidates), .report_wake_head_i(lsq_report_identity_head),')
    name = files[1]
    old = '    parameter integer WAKE_MUX_IMPL = 0,'
    texts[name] = once(texts[name], old, old+'''
    parameter integer REPORT_WAKE_PRECOMPARE = 0,
    parameter integer REPORT_WAKE_LANE = 0,''')
    old = '    input  wire [(WAKE_WIDTH*SOURCE_TAG_WIDTH)-1:0] wake_tag_i,'
    texts[name] = once(texts[name], old, old+'''
    input  wire [(2*SOURCE_TAG_WIDTH)-1:0] report_wake_tags_i,
    input  wire                         report_wake_head_i,''')
    old = '        for (wr = 0; wr < ENTRIES; wr = wr + 1) begin : g_entry'
    texts[name] = once(texts[name], old, '''        wire [WAKE_DOMAINS*2*SOURCE_TAG_WIDTH-1:0] report_tag_views;
        wire [WAKE_DOMAINS-1:0] report_head_views;
        if(REPORT_WAKE_PRECOMPARE!=0) begin:g_report_match_domains
            rv32_frequency_control_tree #(.WIDTH(2*SOURCE_TAG_WIDTH),.LEAVES(WAKE_DOMAINS)) tags (
                .signal_i(report_wake_tags_i),.views_o(report_tag_views));
            rv32_frequency_control_tree #(.LEAVES(WAKE_DOMAINS)) choice (
                .signal_i(report_wake_head_i),.views_o(report_head_views));
        end else begin:g_no_report_match_domains
            assign report_tag_views=0;
            assign report_head_views=0;
        end
'''+old)
    old = '''                assign wake1_match[wr][wl] = local_valid[wl] && local_tags[wl*SOURCE_TAG_WIDTH] &&
                    src1_tag_mem[wr][0] && local_tags[wl*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH] == src1_tag_mem[wr];
                assign wake2_match[wr][wl] = local_valid[wl] && local_tags[wl*SOURCE_TAG_WIDTH] &&
                    src2_tag_mem[wr][0] && local_tags[wl*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH] == src2_tag_mem[wr];'''
    new = '''                if(REPORT_WAKE_PRECOMPARE!=0 && wl==REPORT_WAKE_LANE) begin:g_report_match_before_choice
                    wire [SOURCE_TAG_WIDTH-1:0] saved_tag=
                        report_tag_views[DOMAIN*2*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH];
                    wire [SOURCE_TAG_WIDTH-1:0] head_tag=
                        report_tag_views[DOMAIN*2*SOURCE_TAG_WIDTH+SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH];
                    wire saved1=saved_tag[0] && src1_tag_mem[wr][0] && saved_tag==src1_tag_mem[wr];
                    wire head1=head_tag[0] && src1_tag_mem[wr][0] && head_tag==src1_tag_mem[wr];
                    wire saved2=saved_tag[0] && src2_tag_mem[wr][0] && saved_tag==src2_tag_mem[wr];
                    wire head2=head_tag[0] && src2_tag_mem[wr][0] && head_tag==src2_tag_mem[wr];
                    assign wake1_match[wr][wl]=local_valid[wl] && (report_head_views[DOMAIN]?head1:saved1);
                    assign wake2_match[wr][wl]=local_valid[wl] && (report_head_views[DOMAIN]?head2:saved2);
                end else begin:g_original_selected_match
'''+old+'''
                end'''
    texts[name] = once(texts[name], old, new)
    marker = '                if(WAKE_UNIQUE_OWNER!=0) begin:g_unique_owner'
    assert texts[name][texts[name].index(marker):] == originals[name][originals[name].index(marker):]
    for name in parent['source_sha256']:
        dest = TARGET/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, dest)
    for name, content in texts.items():
        (TARGET/name).write_text(content, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LSQ_PHYSICAL_WAKE_MATCH_BEFORE_REPORT_CHOICE_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(TARGET),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=files,
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], **{FLAG:1})
    record['enabled_profile'] = dict(parent['enabled_profile'],lsq_wake_match_before_head_choice=True,
        lsq_wake_comparison_candidates=2,lsq_wake_match_extra_ff_bits=0,
        lsq_wake_match_extra_sram_bits=0,lsq_wake_match_extra_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'In original direct physical-producer wake mode, export saved/head candidate physical destinations before the existing report choice. Apply identical phys!=0&&phys<PHYS_REGS encoding independently. Each RS operand compares both candidate tags in parallel; original late head choice selects only a match bool under unchanged actual local wake_valid. All other wake columns, first/last duplicate priority, wake values, issue arbitration, recovery/GEN/cancel/hold/state equations remain exact. Existing default0/unsupported profile retains selected-tag comparison; no speculative wake or new edge.'
    ]
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=files,tests_started=False,
        new_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        rs_priority_value_issue_state_suffix_byte_identical=True,
        source_arguments=[
            'A109 RS_DIRECT_WAKE=physical_wakeup&&(COMPLETION_BYPASS1or2) broadcasts the four raw producers plus separate cache return, already bypassing CDB arbitration. In A105 source3 direct_payload.data72 is an alias of raw LSQ producer_phys4 and RS tagtree bit26, not proof that the path traverses CDB selection. It then contributes to physical-valid encoding/tag match. Earlier reports framing this as CDB-tag-before-RS-comparison are superseded by this source audit; original PPA numbers and named timing nodes are unchanged.',
            'In active HEAD_LOAD_PACKET_PRESELECT mode, exact public physical destination is h?head_packet_metadata[TAG_WIDTH+:PHYS_ADDR_WIDTH]:saved_identity_tree[1][ROB_TAG_WIDTH+TAG_WIDTH+33+:PHYS_ADDR_WIDTH]. Those same slices form the private two candidates, including held saved packet selection. Encoding E(p)={p,p!=0&&p<PHYS_REGS} commutes with choice. The original active direct wake tag therefore equals h?E(head):E(saved), with no fullGEN/range weakening because all original wake_valid/unretired/localcancel/currentload filters still apply.',
            'For each old RS operand source tag t, original match=valid&&tag[0]&&t[0]&&tag==t. Substituting tag=h?E(head):E(saved) gives exactly valid&&(h?head_match:saved_match). New comparisons compute each original tagvalid/nonzero/range/equality term before h. Preserve selected source valid, fields and unretired/cancel qualification for all actual wakes. If valid0, both old and new matches0 regardless of unused candidate bits. No speculative wake is created, including stale/cancelled/retired reports.',
            'Only the designated LSQ rawproducer wake column changes its comparison equation; cached return and ALU/MDU or legacy CDB columns remain. All source match vectors are equal, so original first/last duplicate priority, first combinational bypass values, last sequential capture, issue eligibility/age arbitration/recovery-kill/allocation and every RS payload state are equal. New RS input ports are unused in default0 or inactive wake mux profiles. Active guard requires original headidentity, prepared headpacket, directphysicalwake and parallel wakemux; no unsupported tag-width interpretation.',
            'Each four-row domain receives exact candidate tags and headchoice from original functional control trees. With RS8, two operands add16 candidate comparisons while replacing the original selected-column comparator network; dynamic physical-valid encoding is done early per candidate rather than after late packet mux. Area can increase, value routing or actual wakevalid can remain critical. New source is not tested/adopted and does not inherit A109 metrics; original live A109 source/manager/tool/report remains frozen.',
            'BOOM primary documentation distinguishes early ALU wake and writeback wake for loads/variable latency, and puts bypassing at register-read completion. This is context for avoiding extra wake latency, not evidence of a MHz gain in this CPU. Here the exact original same-cycle contract is retained by functional precomparison. No HDL/lint/formal/sim/synthesis/STA/unit tests or CPU builds; target full RV32IM/OoO/inorder/MMIO/parameterization/three metrics unchanged.'
        ],research_sources=[
            'https://docs.boom-core.org/en/latest/sections/issue-units.html',
            'https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html'],
        candidate_metrics=None,goal_complete=False,adopted=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
