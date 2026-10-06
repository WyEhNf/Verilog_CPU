"""Exploit real 16-byte fetch-line alignment in PC generation and bank routing."""
from pathlib import Path
import hashlib,json,shutil

BASE=Path('F:/CPU2026Candidates/lsq_completion_tree_v4_20261003')
STAGE=Path('F:/CPU2026Candidates/aligned_fetch_v5_20261003')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def frontend(text):
    anchor='    wire queue_space = (count_reg + bundle_count <= FQ_DEPTH);'
    extra=r'''
    // Returned words share the line prefix. Only crossing the end of the line
    // needs a carry into that prefix; compute that increment once in parallel.
    wire [27:0] following_line = if_resp_pc_i[31:4] + 28'd1;
    wire [FE_WIDTH*32-1:0] bundle_word_pc, after_word_pc;
    genvar pc_lane;
    generate for(pc_lane=0;pc_lane<FE_WIDTH;pc_lane=pc_lane+1) begin:g_bundle_pc
        wire [2:0] word = {1'b0,if_resp_pc_i[3:2]} + pc_lane;
        wire [2:0] after_word = {1'b0,if_resp_pc_i[3:2]} + pc_lane + 1;
        // bundle_word_pc is consumed only for word<4, so no line carry exists.
        assign bundle_word_pc[pc_lane*32 +: 32] =
            {if_resp_pc_i[31:4],word[1:0],if_resp_pc_i[1:0]};
        assign after_word_pc[pc_lane*32 +: 32] =
            {after_word[2]?following_line:if_resp_pc_i[31:4],after_word[1:0],if_resp_pc_i[1:0]};
    end endgenerate
'''
    assert text.count(anchor)==1
    text=text.replace(anchor,extra+'\n'+anchor,1)
    assert text.count("next_pc_comb = if_resp_pc_i + 32'd4;")==1
    assert text.count("bundle_pc[b*32 +: 32] = if_resp_pc_i + (b*32'd4);")==1
    assert text.count("next_pc_comb = if_resp_pc_i + ((b+1)*32'd4);")==1
    text=text.replace("next_pc_comb = if_resp_pc_i + 32'd4;","next_pc_comb = after_word_pc[0 +: 32];")
    text=text.replace("bundle_pc[b*32 +: 32] = if_resp_pc_i + (b*32'd4);","bundle_pc[b*32 +: 32] = bundle_word_pc[b*32 +: 32];")
    text=text.replace("next_pc_comb = if_resp_pc_i + ((b+1)*32'd4);","next_pc_comb = after_word_pc[b*32 +: 32];")
    return text

def predictor(text):
    old=r'''            wire [31:0] pc = query_pc_i + {28'd0, offset, 2'b00};
            wire [127:0] shifted_line = query_line_i >> (word_index * 32);
            wire [31:0] inst = shifted_line[31:0];'''
    new=r'''            wire [31:0] pc,inst;
            if(FE_WIDTH==4) begin:g_word_bank
                // Each bank owns one physical word in this returned line.
                // word_index<4 masks banks preceding the first requested word.
                assign pc={query_pc_i[31:4],BANK_NUMBER,query_pc_i[1:0]};
                assign inst=query_line_i[bank*32 +: 32];
            end else begin:g_rotated_bank
                assign pc=query_pc_i + {28'd0,offset,2'b00};
                wire [127:0] shifted_line=query_line_i >> (word_index*32);
                assign inst=shifted_line[31:0];
            end'''
    assert text.count(old)==1
    return text.replace(old,new,1)

def main():
    assert not STAGE.exists(),'Preserve previous candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for n,h in manifest['source_sha256'].items():
        assert sha(BASE/n)==h.lower(),n
        p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/n,p)
    for name,transform in [('rtl/frontend/rv32_fetch_frontend.v',frontend),('rtl/predictor/rv32_banked_predictor.v',predictor)]:
        p=STAGE/name;p.write_text(transform(p.read_text(encoding='utf-8')),encoding='utf-8')
        manifest['changed'].append(dict(file=name,change='Use aligned-line PC fields and fixed physical word banks'))
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},tool_sha256=sha(__file__),
        strategy=manifest['strategy']+'; aligned fetch PCs and fixed four-word predictor routing without added latency')
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True)))

if __name__=='__main__':main()
