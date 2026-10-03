"""Replace LSQ's head-relative completion scan with static balanced choices."""
from pathlib import Path
import hashlib, json, shutil

BASE=Path('F:/CPU2026Candidates/issue_credit_queue_v3_20261003')
STAGE=Path('F:/CPU2026Candidates/lsq_completion_tree_v4_20261003')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

TREE=r'''
    // One narrow physical-row age comparison per row and a logarithmic tree.
    // Payload travels beside the winner, avoiding a second indexed read after
    // the head-relative scan. Completion order and handshake latency are kept.
    wire completion_valid_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] completion_age_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] completion_slot_tree [1:2*LSQ_ENTRIES-1];
    wire [ROB_TAG_WIDTH-1:0] completion_rob_tree [1:2*LSQ_ENTRIES-1];
    wire [TAG_WIDTH-1:0] completion_lsq_tree [1:2*LSQ_ENTRIES-1];
    wire [31:0] completion_value_tree [1:2*LSQ_ENTRIES-1];
    wire completion_error_tree [1:2*LSQ_ENTRIES-1];
    genvar completion_row,completion_node;
    generate
        for(completion_row=0;completion_row<LSQ_ENTRIES;completion_row=completion_row+1) begin:g_completion_row
            assign completion_valid_tree[LSQ_ENTRIES+completion_row] =
                entry_age[completion_row]<occupancy_reg && valid_mem[completion_row] &&
                load_mem[completion_row] && complete_mem[completion_row] &&
                !load_reported_mem[completion_row];
            assign completion_age_tree[LSQ_ENTRIES+completion_row]=entry_age[completion_row];
            assign completion_slot_tree[LSQ_ENTRIES+completion_row]=completion_row;
            assign completion_rob_tree[LSQ_ENTRIES+completion_row]=rob_tag_mem[completion_row];
            assign completion_lsq_tree[LSQ_ENTRIES+completion_row]=
                make_lsq_tag(completion_row,generation_mem[completion_row]);
            assign completion_value_tree[LSQ_ENTRIES+completion_row]=complete_value_mem[completion_row];
            assign completion_error_tree[LSQ_ENTRIES+completion_row]=complete_error_mem[completion_row];
        end
        for(completion_node=1;completion_node<LSQ_ENTRIES;completion_node=completion_node+1) begin:g_completion_node
            wire left_wins=completion_valid_tree[2*completion_node] &&
                (!completion_valid_tree[2*completion_node+1] ||
                 completion_age_tree[2*completion_node]<=completion_age_tree[2*completion_node+1]);
            assign completion_valid_tree[completion_node]=
                completion_valid_tree[2*completion_node] || completion_valid_tree[2*completion_node+1];
            assign completion_age_tree[completion_node]=left_wins?
                completion_age_tree[2*completion_node]:completion_age_tree[2*completion_node+1];
            assign completion_slot_tree[completion_node]=left_wins?
                completion_slot_tree[2*completion_node]:completion_slot_tree[2*completion_node+1];
            assign completion_rob_tree[completion_node]=left_wins?
                completion_rob_tree[2*completion_node]:completion_rob_tree[2*completion_node+1];
            assign completion_lsq_tree[completion_node]=left_wins?
                completion_lsq_tree[2*completion_node]:completion_lsq_tree[2*completion_node+1];
            assign completion_value_tree[completion_node]=left_wins?
                completion_value_tree[2*completion_node]:completion_value_tree[2*completion_node+1];
            assign completion_error_tree[completion_node]=left_wins?
                completion_error_tree[2*completion_node]:completion_error_tree[2*completion_node+1];
        end
    endgenerate
'''

def main():
    assert not STAGE.exists(),'Preserve earlier candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for name,h in manifest['source_sha256'].items():
        assert sha(BASE/name)==h.lower(),name
        p=STAGE/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,p)
    p=STAGE/'rtl/backend/rv32_lsq.v';text=p.read_text(encoding='utf-8')
    start=text.index("        complete_slot_found = 1'b0;")
    stop=text.index('        if (occupancy_reg != 0 && valid_mem[head_reg]) begin',start)
    text=text[:start]+r'''        complete_slot_found = completion_valid_tree[1];
        complete_slot_select = completion_valid_tree[1] ? completion_slot_tree[1] : head_reg;
        if (completion_valid_tree[1]) begin
            load_complete_valid_o = 1'b1;
            load_complete_rob_tag_o = completion_rob_tree[1];
            load_complete_lsq_tag_o = completion_lsq_tree[1];
            load_complete_value_o = completion_value_tree[1];
            load_complete_error_o = completion_error_tree[1];
        end
'''+text[stop:]
    anchor='    always @* begin\n        load_complete_valid_o'
    assert text.count(anchor)==1
    text=text.replace(anchor,TREE+'\n'+anchor,1)
    p.write_text(text,encoding='utf-8')
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},
        strategy=manifest['strategy']+'; balanced static-row LSQ completion selection carrying payload alongside age',
        tool_sha256=sha(__file__))
    manifest['changed'].append(dict(file='rtl/backend/rv32_lsq.v',change='Balanced completion selection; preserve oldest eligible result'))
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True)))

if __name__=='__main__':main()
