"""Use the frontend's existing pending PC before late I-cache reply selection."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A43_dcache_hit_response_coissue'
TARGET = BASE/'A44_frontend_local_response_pc'
CRITICAL = Path('F:/CPU2026Proofs/ER1_A41_critical_frontend_owner_20261005.json')


def once(text, old, new):
    assert text.count(old)==1, old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    path_proof=read(CRITICAL)
    assert path_proof['source_manifest_sha256']=='74bf209fd0a9b8288d429acd569401d2d56830b61901d29464e15395fcc228ea'
    assert any(a['signal']=='core.frontend.bundle_pc'
        for row in path_proof['attributed_cells'] for a in row['output_aliases'])
    changes={}
    name='rtl/frontend/rv32_fetch_frontend.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer RESPONSE_BYPASS = 0,',
        '    parameter integer RESPONSE_BYPASS = 0,\n    parameter integer RESPONSE_LOCAL_PC = 0,')
    text=once(text,'    input  wire [31:0]                  if_resp_pc_i,',
        '    input  wire [31:0]                  if_resp_pc_i,\n    output wire [31:0]                  response_base_pc_o,')
    text=once(text,'''    wire [31:0] pc_reg;
    wire [EPOCH_WIDTH-1:0] epoch_reg;''', '''    wire [31:0] pc_reg;
    // One pending request: pc_reg stays at its offered/accepted PC until its
    // response is consumed. On a chained edge, the same next_pc writes this
    // owner and is offered to the next request. No extra pending-PC state.
    wire [31:0] response_base_pc=(RESPONSE_LOCAL_PC!=0)?pc_reg:if_resp_pc_i;
    assign response_base_pc_o=response_base_pc;
    wire [EPOCH_WIDTH-1:0] epoch_reg;''')
    text=once(text,'''    wire response_live = (if_resp_epoch_i == epoch_reg) &&
                         (if_resp_line_addr_i == {if_resp_pc_i[31:4], 4'b0000});''', '''    wire response_identity_live=(RESPONSE_LOCAL_PC==0) ||
        (req_pending_reg && if_resp_pc_i==pc_reg);
    wire response_live = (if_resp_epoch_i == epoch_reg) &&
                         (if_resp_line_addr_i == {if_resp_pc_i[31:4], 4'b0000}) &&
                         response_identity_live;''')
    marker='    // Only bundle_count authorizes enqueue;'
    start=text.index(marker)
    text=text[:start]+text[start:].replace('if_resp_pc_i','response_base_pc')
    # Keep exactly the original PC/epoch owners, their event precedence,
    # queue allocation, request pending transitions and pipeline edges.
    for begin,end in (('    wire [31:0] pc_update;','    wire [1:0] chain_views;'),
                      ('    always @(posedge clk_i) begin','endmodule')):
        assert text[text.index(begin):text.index(end,text.index(begin))]==original[original.index(begin):original.index(end,original.index(begin))]
    assert len(re.findall(r'^\s*reg\s+',text,re.M))==len(re.findall(r'^\s*reg\s+',original,re.M))
    changes[name]=text

    name='rtl/cpu_core.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer FRONTEND_RESPONSE_BYPASS = 0,',
        '    parameter integer FRONTEND_RESPONSE_BYPASS = 0,\n    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 0,')
    text=once(text,'    wire [31:0] if_resp_pc, if_resp_line_addr;',
        '    wire [31:0] if_resp_pc, if_resp_line_addr;\n    wire [31:0] response_base_pc;')
    begin=text.index('    // Consecutive lane PCs route to disjoint low-index predictor banks.')
    end=text.index('    // The first accepted call wins;',begin)
    text=text[:begin]+text[begin:end].replace('if_resp_pc','response_base_pc')+text[end:]
    text=once(text,'.RESPONSE_BYPASS(FRONTEND_RESPONSE_BYPASS && (DECODE_PIPELINE!=0) && !SERIAL_BACKEND),',
        '''.RESPONSE_BYPASS(FRONTEND_RESPONSE_BYPASS && (DECODE_PIPELINE!=0) && !SERIAL_BACKEND),
        .RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC && (ENABLE_CACHES!=0) &&
            (ICACHE_MSHRS>1) && (ICACHE_COMBINATIONAL_HIT==0) && !SERIAL_BACKEND),''')
    text=once(text,'.if_resp_ready_o(if_resp_ready), .if_resp_pc_i(if_resp_pc),',
        '.if_resp_ready_o(if_resp_ready), .if_resp_pc_i(if_resp_pc), .response_base_pc_o(response_base_pc),')
    assert text[text.index('    wire ic_mem_req_valid,'):]==original[original.index('    wire ic_mem_req_valid,'):]
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer FRONTEND_RESPONSE_BYPASS = 1,',
        '    parameter integer FRONTEND_RESPONSE_BYPASS = 1,\n    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 1,')
    text=once(text,'.FRONTEND_RESPONSE_BYPASS(FRONTEND_RESPONSE_BYPASS),',
        '.FRONTEND_RESPONSE_BYPASS(FRONTEND_RESPONSE_BYPASS), .FRONTEND_RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC),')
    changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],FRONTEND_RESPONSE_LOCAL_PC=1)
    record['enabled_profile']=dict(parent['enabled_profile'],frontend_local_response_pc=True,
        frontend_local_response_pc_added_ff_bits=0,
        frontend_local_response_pc_added_sram_bits=0,
        frontend_local_response_pc_added_pipeline_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Use existing frontend pc_reg for predictor/RAS queries, word/lane selection, bundle PCs and sequential next PCs in the native synchronous nonblocking-cache profile. Require a pending request and exact reply PC plus original epoch/line qualification before any response acceptance. Keep chained request timing and all PC owner/recovery/queue transitions.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        frontend_local_response_pc={
            'a41_existing_critical_path_proof':str(CRITICAL),
            'a41_existing_critical_path_proof_sha256':sha(CRITICAL),
            'old_path':'late Icache reply-PC selection -> lane PCs/gshare index -> BHT -> chained request PC',
            'new_data_source':'existing pending frontend pc_reg, available before reply-PC selection',
            'response_qualification':'pending plus exact reply PC plus original epoch/line',
            'added_ff_bits':0,'added_sram_bits':0,'added_pipeline_edges':0,
            'frequency_and_area_unmeasured':True})
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_FRONTEND_LOCAL_RESPONSE_PC_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),
        added_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,tests_started=False,adopted=False,
        source_arguments=[
            'One request can be pending. Before an accepted response pc_reg remains at the offered/accepted request PC; request acceptance alone does not update it. On response acceptance, next_pc updates it and is offered to a chained request at that exact edge. If the chained request stalls, req_pending clears and the saved next PC is offered again until accepted.',
            'Redirect owns the original higher-priority PC/epoch update and clears pending. No response can consume at reset/redirect. New enabled-mode qualification requires pending and exact returned PC, in addition to the original epoch and cache-line address equality; stale or unsolicited replies cannot publish a local-PC packet.',
            'Every predictor bank, RAS instruction/return-address query, frontend word/lane index, bundle PC and sequential/default next PC uses the same response_base_pc. Returned instruction line and all prediction/history metadata stay with the accepted response. No data/PC mismatch is permitted by the new identity gate.',
            'The existing A41 critical path traverses line-filter response selection, bundle_pc, gshare bank_training_index, BHT query and chained if_req_pc. Local PC removes the response-PC select from these data paths; the new PC comparison remains a late acceptance guard. Actual new critical path/area/frequency are unknown.',
            'No additional pending PC register, payload state, SRAM or pipeline edge. Original PC/epoch owner source, queue/pending clocked state, dispatch/backend/cache logic remain exact. Stronger identity comparison may add combinational gates; area is not assumed unchanged.',
            'Default0 retains the original response-PC calculations. Core enables local mode only for cached nonblocking synchronous-hit profiles with ICACHE_MSHRS>1 and serial backend disabled; uncached/blocking/combinational-hit profiles retain old behavior.',
            'No HDL/lint/simulation/synthesis/STA/unit tests. Later coverage must include all PC word offsets and FE widths, warm chaining, stalled next request, empty/occupied queue, response backpressure, wrong PC/line/epoch, redirects with outstanding misses, error/freeze and fallback profiles.'
        ])
    write(BASE/'A44_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__=='__main__':
    main()
