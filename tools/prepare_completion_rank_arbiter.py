"""Parallelize direct completion arbitration without a new result stage."""
from pathlib import Path
import hashlib,json,shutil

BASE=Path('F:/CPU2026Candidates/bounded_controls_v7_20261003')
STAGE=Path('F:/CPU2026Candidates/completion_rank_v8_20261003')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

ARBITER=r'''
    // Reserve held sources using static tag comparisons. Each remaining
    // source computes its rank in the round-robin order in parallel. Free
    // lane numbers select ranks, rather than re-scanning a variable-indexed
    // source array once for each lane.
    localparam integer RANK_WIDTH=(SOURCES<=1)?1:$clog2(SOURCES+1);
    localparam integer RANK_LEAVES=1<<$clog2(SOURCES);
    wire [SOURCES-1:0] held_source_mask [0:CDB_WIDTH-1];
    wire [CDB_WIDTH-1:0] held_lane_live;
    wire [SOURCE_WIDTH-1:0] source_distance [0:SOURCES-1];
    wire [RANK_WIDTH-1:0] source_rank [0:SOURCES-1];
    wire [RANK_WIDTH-1:0] lane_free_rank [0:CDB_WIDTH-1];
    wire [SOURCES-1:0] selected_mask [0:CDB_WIDTH-1];
    genvar rank_source,rank_other,rank_node,rank_lane,rank_prior_lane;
    generate
        for(rank_source=0;rank_source<SOURCES;rank_source=rank_source+1) begin:g_source_rank
            localparam [SOURCE_WIDTH:0] NUMBER=rank_source;
            localparam [SOURCE_WIDTH:0] SOURCE_COUNT=SOURCES;
            wire [SOURCE_WIDTH:0] distance_full=NUMBER+
                ((direct_rr_reg>NUMBER)?SOURCE_COUNT:0)-direct_rr_reg;
            assign source_distance[rank_source]=distance_full[0 +: SOURCE_WIDTH];
            assign direct_eligible[rank_source]=producer_valid_i[rank_source] &&
                producer_target_live_i[rank_source] && producer_tag_i[rank_source*TAG_WIDTH] &&
                (!live_tag_valid_i || producer_tag_i[rank_source*TAG_WIDTH +: TAG_WIDTH]==live_tag_i);
            wire [CDB_WIDTH-1:0] held_here;
            for(rank_prior_lane=0;rank_prior_lane<CDB_WIDTH;rank_prior_lane=rank_prior_lane+1) begin:g_held
                assign held_here[rank_prior_lane]=held_source_mask[rank_prior_lane][rank_source];
            end
            assign direct_used[rank_source]=|held_here;
            wire [RANK_WIDTH-1:0] earlier_count [1:2*RANK_LEAVES-1];
            for(rank_other=0;rank_other<RANK_LEAVES;rank_other=rank_other+1) begin:g_earlier
                if(rank_other<SOURCES) begin:g_source
                    assign earlier_count[RANK_LEAVES+rank_other]=
                        direct_eligible[rank_other] && !direct_used[rank_other] &&
                        source_distance[rank_other]<source_distance[rank_source];
                end else begin:g_padding
                    assign earlier_count[RANK_LEAVES+rank_other]=0;
                end
            end
            for(rank_node=1;rank_node<RANK_LEAVES;rank_node=rank_node+1) begin:g_count
                assign earlier_count[rank_node]=earlier_count[2*rank_node]+earlier_count[2*rank_node+1];
            end
            assign source_rank[rank_source]=earlier_count[1];
        end
        for(rank_lane=0;rank_lane<CDB_WIDTH;rank_lane=rank_lane+1) begin:g_lane_rank
            for(rank_source=0;rank_source<SOURCES;rank_source=rank_source+1) begin:g_held_match
                assign held_source_mask[rank_lane][rank_source]=direct_hold_valid[rank_lane] &&
                    direct_hold_source[rank_lane]==rank_source && direct_eligible[rank_source] &&
                    producer_tag_i[rank_source*TAG_WIDTH +: TAG_WIDTH]==direct_hold_tag[rank_lane];
                assign selected_mask[rank_lane][rank_source]=held_source_mask[rank_lane][rank_source] ||
                    (!held_lane_live[rank_lane] && direct_eligible[rank_source] && !direct_used[rank_source] &&
                     source_rank[rank_source]==lane_free_rank[rank_lane]);
            end
            assign held_lane_live[rank_lane]=|held_source_mask[rank_lane];
            wire [RANK_WIDTH-1:0] free_prefix [0:rank_lane];
            assign free_prefix[0]=0;
            for(rank_prior_lane=0;rank_prior_lane<rank_lane;rank_prior_lane=rank_prior_lane+1) begin:g_free_prefix
                assign free_prefix[rank_prior_lane+1]=free_prefix[rank_prior_lane]+!held_lane_live[rank_prior_lane];
            end
            assign lane_free_rank[rank_lane]=free_prefix[rank_lane];
        end
    endgenerate
    always @* begin
        direct_selected_valid=0;
        direct_rr_next=direct_rr_reg;
        for(direct_lane=0;direct_lane<CDB_WIDTH;direct_lane=direct_lane+1) begin
            direct_selected_source[direct_lane]=0;
            direct_selected_valid[direct_lane]=|selected_mask[direct_lane];
            for(direct_source=0;direct_source<SOURCES;direct_source=direct_source+1)
                direct_selected_source[direct_lane]=direct_selected_source[direct_lane] |
                    ({SOURCE_WIDTH{selected_mask[direct_lane][direct_source]}} & direct_source);
            // Retain the exact old cursor rule: last accepted lane wins.
            if(direct_selected_valid[direct_lane] && cdb_ready_i[direct_lane]) begin
                if(direct_selected_source[direct_lane]==SOURCES-1) direct_rr_next=0;
                else direct_rr_next=direct_selected_source[direct_lane]+1'b1;
            end
        end
    end
'''

def main():
    assert not STAGE.exists(),'Preserve previous candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for n,h in manifest['source_sha256'].items():
        assert sha(BASE/n)==h.lower(),n
        p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/n,p)
    name='rtl/backend/rv32_completion_network.v';p=STAGE/name;text=p.read_text(encoding='utf-8')
    old='    reg [SOURCES-1:0] direct_eligible, direct_used;'
    assert text.count(old)==1
    text=text.replace(old,'    wire [SOURCES-1:0] direct_eligible, direct_used;',1)
    start=text.index('    // Reserve ALL held lanes before filling any unheld lane.')
    stop=text.index('    always @(posedge clk_i) begin',start)
    text=text[:start]+ARBITER+'\n'+text[stop:]
    p.write_text(text,encoding='utf-8')
    manifest['changed'].append(dict(file=name,change='Parallel source ranks with static tag comparison; preserve held lanes and cursor'))
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},tool_sha256=sha(__file__),
        strategy=manifest['strategy']+'; parallel completion source ranking instead of per-lane dynamic scans')
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True)))

if __name__=='__main__':main()
