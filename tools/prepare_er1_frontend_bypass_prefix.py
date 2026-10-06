"""Shorten new empty-FQ bypass validity path using explicit instruction prefix."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A30_frontend_response_bypass'
TARGET=BASE/'A31_frontend_bypass_prefix'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    name='rtl/frontend/rv32_fetch_frontend.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'''    // Response acceptance depends on saved occupancy/epoch, never on decode
    // readiness. Empty-queue bypass therefore has no ready-to-valid loop.
    wire response_bypass=(RESPONSE_BYPASS!=0) && count_reg==0 &&
        if_resp_valid_i && if_resp_ready_o && !if_resp_error_i &&
        !frozen_reg && !stop_i && !error_i;
    wire [31:0] output_available=response_bypass?
        {{(32-BUNDLE_COUNT_WIDTH){1'b0}},bundle_count}:count_reg;''','''    // Legal FQ_DEPTH>=FE_WIDTH and bundle_count<=FE_WIDTH guarantee space
    // when empty. Do not put the full bundle count/space adder on the bypass
    // valid path; this predicate still implies original response acceptance.
    wire response_bypass=(RESPONSE_BYPASS!=0) && count_reg==0 &&
        !reset_i && !redirect_valid_i && response_live &&
        if_resp_valid_i && !if_resp_error_i && !frozen_reg && !stop_i && !error_i;
    wire [FE_WIDTH-1:0] bypass_prefix,bypass_lane_valid;''')
    text=once(text,'    genvar response_lane,response_half,public_lane;',
        '    genvar response_lane,response_half,public_lane,bypass_lane;')
    text=once(text,'''    generate
        for(response_lane=0;response_lane<FE_WIDTH;response_lane=response_lane+1) begin:g_response_lane''','''    generate
        for(bypass_lane=0;bypass_lane<FE_WIDTH;bypass_lane=bypass_lane+1) begin:g_bypass_prefix
            if(bypass_lane==0) begin:g_first
                assign bypass_prefix[bypass_lane]=1'b1;
            end else begin:g_later
                assign bypass_prefix[bypass_lane]=bypass_prefix[bypass_lane-1] &&
                    !if_resp_pred_taken_i[bypass_lane-1] &&
                    !((LEGACY_SENTINEL_HALT!=0) &&
                      response_words[(bypass_lane-1)*32 +: 32]==32'h0ff00513);
            end
            wire [2:0] word_number={1'b0,if_resp_pc_i[3:2]}+3'(bypass_lane);
            assign bypass_lane_valid[bypass_lane]=response_bypass && bypass_prefix[bypass_lane] &&
                word_number<3'd4;
        end
        for(response_lane=0;response_lane<FE_WIDTH;response_lane=response_lane+1) begin:g_response_lane''')
    text=once(text,'.events_i({response_bypass && public_lane<bundle_count,',
        '.events_i({bypass_lane_valid[public_lane],')
    text=once(text,'''            if (j < output_available) begin
                fetch_valid_o[j] = 1'b1;
            end
            if ((j < output_available) && (deq_count == j) && fetch_ready_i[j])''','''            if(response_bypass) fetch_valid_o[j]=bypass_lane_valid[j];
            else if(j<count_reg) fetch_valid_o[j]=1'b1;
            if(fetch_valid_o[j] && (deq_count == j) && fetch_ready_i[j])''')
    clock='    always @(posedge clk_i) begin\n        if (reset_i) begin'
    assert text[text.index(clock):]==original[original.index(clock):]
    assert 'FQ_DEPTH < FE_WIDTH' in original
    assert 'for (b = 0; b < FE_WIDTH; b = b + 1)' in original
    for file in parent['source_sha256']:
        dest=TARGET/file;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/file,dest)
    (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Qualify empty-FQ bypass by saved empty/epoch/response guards and explicit per-lane prediction prefix, removing total bundle-count/queue-space arithmetic from decode validity.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        frontend_bypass_first_lane_requires_direction_prediction=False,
        frontend_bypass_valid_requires_total_bundle_count=False,
        frontend_bypass_added_state_bits=0,frontend_bypass_prefix_fmax_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_EMPTY_FQ_BYPASS_VALID_PREFIX_COUNT_ADDER_REMOVED_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=[name],tests_started=False,
        source_arguments=[
            'Existing legal-parameter check requires FQ_DEPTH>=FE_WIDTH; bundle loop counts at mostFE_WIDTH. Thus empty saved FQ guarantees original queue_space, and reset/redirect/response_live guards imply if_resp_ready without depending on its bundle-count/space adder.',
            'Explicit prefix admits a lane only when its word index is in the line and no earlier lane predicted taken or legacy sentinel halt. This is the same contiguous accepted bundle as the unchanged bundle_count loop.',
            'Lane0 validity needs only saved empty/epoch/response/error guards and valid word index, not direction prediction. Lane1 additionally needs only lane0 prediction/sentinel; unused wider public lanes can be pruned by the two-wide decoder.',
            'Original response acceptance, entire bundle writes, enq_count, PC/epoch/queue/head/tail/count clocks are exact parent source. Bypassed deq remains a prefixK<=acceptedN, so count/pointers remain as A30.',
            'No new state or latency change vsA30; structural removal of count arithmetic shortens only the new control cone. Predictor metadata and decoder data paths still need actual timing measurement.',
            'Source reasoning only; no formal equivalence, HDL lint/build, CPU/unit simulation, synthesis or STA. Unknown/X and invalid parameter inputs are not claimed supported beyond original contracts.'
        ])
    write(BASE/'A31_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
