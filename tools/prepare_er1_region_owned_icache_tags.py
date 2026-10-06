"""Share exact instruction address prefix per way; preserve full hit identity."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A31_frontend_bypass_prefix'
TARGET=BASE/'A32_region_owned_icache_tags'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/cache/rv32_icache_nonblocking.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer TAG_MATCH_PARALLEL = 0,',
        '    parameter integer TAG_MATCH_PARALLEL = 0,\n    parameter integer TAG_REGION_BITS = 0,')
    text=once(text,'    wire [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];','''    wire [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];
    localparam integer TAG_STORED_WIDTH=CACHE_TAG_WIDTH-TAG_REGION_BITS;
    localparam integer REGION_STORAGE_WIDTH=(TAG_REGION_BITS>0)?TAG_REGION_BITS:1;
    wire [CACHE_WAYS*REGION_STORAGE_WIDTH-1:0] tag_regions;
    wire [CACHE_LINES-1:0] region_invalidate;
    wire [CACHE_LINES*3-1:0] region_match_views;
    genvar region_way;
    generate if(TAG_REGION_BITS!=0) begin:g_region_owners
        for(region_way=0;region_way<CACHE_WAYS;region_way=region_way+1) begin:g_way
            wire region_write=refill_array_write && ((refill_entry%CACHE_WAYS)==region_way);
            wire [REGION_STORAGE_WIDTH-1:0] prefix;
            wire region_change=region_write && prefix!=mem_resp_line_addr_i[31 -: REGION_STORAGE_WIDTH];
            wire [CACHE_SETS-1:0] invalidations;
            rv32_frequency_word_bank #(.WIDTH(REGION_STORAGE_WIDTH)) region_owner (
                .clk_i(clk_i),.write_i(region_write),
                .data_i(mem_resp_line_addr_i[31 -: REGION_STORAGE_WIDTH]),.data_o(prefix));
            assign tag_regions[region_way*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH]=prefix;
            rv32_frequency_control_tree #(.LEAVES(CACHE_SETS)) invalidate_tree (
                .signal_i(region_change),.views_o(invalidations));
            for(genvar region_set=0;region_set<CACHE_SETS;region_set=region_set+1) begin:g_set
                assign region_invalidate[region_set*CACHE_WAYS+region_way]=invalidations[region_set];
            end
        end
    end else begin:g_no_regions
        assign tag_regions=0;
        assign region_invalidate=0;
    end endgenerate''')
    # Share each high-prefix comparison before row qualification, then bound
    # its fanout. Replicating full prefix into every row comparator would save
    # only storage and create a large new common-prefix electrical load.
    text=once(text,'    genvar match_row;','''    generate if(TAG_REGION_BITS!=0 && TAG_MATCH_PARALLEL!=0) begin:g_region_queries
        localparam integer DOMAIN_SETS=CACHE_SETS/4;
        for(genvar query_way=0;query_way<CACHE_WAYS;query_way=query_way+1) begin:g_way
            wire [4*REGION_STORAGE_WIDTH-1:0] prefixes;
            rv32_frequency_control_tree #(.WIDTH(REGION_STORAGE_WIDTH),.LEAVES(4)) prefix_tree (
                .signal_i(tag_regions[query_way*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH]),
                .views_o(prefixes));
            for(genvar query_domain=0;query_domain<4;query_domain=query_domain+1) begin:g_domain
                wire [REGION_STORAGE_WIDTH-1:0] prefix=prefixes[query_domain*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH];
                wire [31:0] demand=demand_pc_views[query_domain*32 +: 32];
                wire [31:0] prefetch=prefetch_pc_views[query_domain*32 +: 32];
                wire [31:0] control=control_pc_views[query_domain*32 +: 32];
                wire [DOMAIN_SETS*3-1:0] matches;
                rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(DOMAIN_SETS)) match_tree (
                    .signal_i({prefix==control[31 -: REGION_STORAGE_WIDTH],
                        prefix==prefetch[31 -: REGION_STORAGE_WIDTH],
                        prefix==demand[31 -: REGION_STORAGE_WIDTH]}),.views_o(matches));
                for(genvar query_row=0;query_row<DOMAIN_SETS;query_row=query_row+1) begin:g_row
                    localparam integer ROW=(query_domain*DOMAIN_SETS+query_row)*CACHE_WAYS+query_way;
                    assign region_match_views[ROW*3 +: 3]=matches[query_row*3 +: 3];
                end
            end
        end
    end else begin:g_no_region_queries
        assign region_match_views={CACHE_LINES*3{1'b1}};
    end endgenerate
    genvar match_row;''')
    text=once(text,'tag_mem[match_row]==demand_pc[31:CACHE_SET_WIDTH+4];',
        'region_match_views[match_row*3] &&\n                 tag_mem[match_row][TAG_STORED_WIDTH-1:0]==demand_pc[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4];')
    text=once(text,'tag_mem[match_row]==prefetch_pc[31:CACHE_SET_WIDTH+4];',
        'region_match_views[match_row*3+1] &&\n                 tag_mem[match_row][TAG_STORED_WIDTH-1:0]==prefetch_pc[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4];')
    text=once(text,'tag_mem[match_row]==control_pc[31:CACHE_SET_WIDTH+4];',
        'region_match_views[match_row*3+2] &&\n                 tag_mem[match_row][TAG_STORED_WIDTH-1:0]==control_pc[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4];')
    text=once(text,'    localparam integer TAG_WRITE_WIDTH=CACHE_ENTRY_WIDTH+CACHE_TAG_WIDTH;',
        '    localparam integer TAG_WRITE_WIDTH=CACHE_ENTRY_WIDTH+TAG_STORED_WIDTH;')
    text=once(text,'.signal_i({refill_entry,mem_resp_line_addr_i[31:CACHE_SET_WIDTH+4]}),',
        '.signal_i({refill_entry,mem_resp_line_addr_i[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4]}),')
    text=once(text,'            wire [CACHE_TAG_WIDTH-1:0] local_refill_tag;',
        '            wire [TAG_STORED_WIDTH-1:0] local_refill_tag;')
    text=once(text,"                else if(tag_write) valid_q<=1'b1;",'''                else if(tag_write) valid_q<=1'b1;
                // New fill remains valid; all other rows in the changed way
                // lose validity on the same edge as its new exact prefix.
                else if(region_invalidate[metadata_entry]) valid_q<=1'b0;''')
    text=once(text,'''            rv32_frequency_word_bank #(.WIDTH(CACHE_TAG_WIDTH)) tag_owner (
                .clk_i(clk_i),.write_i(tag_write),.data_i(local_refill_tag),.data_o(tag_mem[metadata_entry]));''','''            wire [TAG_STORED_WIDTH-1:0] stored_tag;
            rv32_frequency_word_bank #(.WIDTH(TAG_STORED_WIDTH)) tag_owner (
                .clk_i(clk_i),.write_i(tag_write),.data_i(local_refill_tag),.data_o(stored_tag));
            if(TAG_REGION_BITS!=0) begin:g_exact_region_tag
                assign tag_mem[metadata_entry]={
                    tag_regions[(metadata_entry%CACHE_WAYS)*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH],stored_tag};
            end else begin:g_full_tag
                assign tag_mem[metadata_entry]=stored_tag;
            end''')
    text=once(text,'''        if ((MSHR_STATE_BANKS != 0) && (MSHR_STATIC_WRITES == 0))''','''        if(TAG_REGION_BITS<0 || TAG_REGION_BITS>=CACHE_TAG_WIDTH)
            $fatal(1,"Instruction cache region bits must be0..CACHE_TAG_WIDTH-1");
        if ((MSHR_STATE_BANKS != 0) && (MSHR_STATIC_WRITES == 0))''')
    # Core data-port arbitration, response storage and every MSHR clock remain
    # unchanged. The instruction filter is entirely unchanged.
    response='    integer prefetch_count;'
    before_init='    initial begin\n        if ((MSHR_STATE_BANKS'
    assert text[text.index(response):text.index('    initial begin\n        if(TAG_REGION_BITS')]==original[original.index(response):original.index(before_init)]
    filter_marker='module rv32_instruction_line_filter #('
    assert text[text.index(filter_marker):]==original[original.index(filter_marker):]
    changes[name]=text
    name='rtl/cpu_core.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer ICACHE_TAG_MATCH_PARALLEL = 0,',
        '    parameter integer ICACHE_TAG_MATCH_PARALLEL = 0,\n    parameter integer ICACHE_TAG_REGION_BITS = 0,')
    text=once(text,'.MSHR_ENTRIES(ICACHE_MSHRS), .TAG_MATCH_PARALLEL(ICACHE_TAG_MATCH_PARALLEL),',
        '.MSHR_ENTRIES(ICACHE_MSHRS), .TAG_REGION_BITS(ICACHE_TAG_REGION_BITS), .TAG_MATCH_PARALLEL(ICACHE_TAG_MATCH_PARALLEL),')
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer ICACHE_TAG_MATCH_PARALLEL = 1,',
        '    parameter integer ICACHE_TAG_MATCH_PARALLEL = 1,\n    parameter integer ICACHE_TAG_REGION_BITS = 12,')
    text=once(text,'.ICACHE_TAG_MATCH_PARALLEL(ICACHE_TAG_MATCH_PARALLEL),',
        '.ICACHE_TAG_MATCH_PARALLEL(ICACHE_TAG_MATCH_PARALLEL), .ICACHE_TAG_REGION_BITS(ICACHE_TAG_REGION_BITS),')
    changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],ICACHE_TAG_REGION_BITS=12)
    record['enabled_profile']=dict(parent['enabled_profile'],ICACHE_TAG_REGION_BITS=12,
        icache_lines=128,icache_ways=2,icache_region_size_bytes=1<<20,
        icache_stored_low_tag_bits=10,icache_way_prefix_state_bits=24,
        icache_removed_tag_ff_bits=128*12-24)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Share exact12-bit instruction-address region prefix per cache way; retain128-line data capacity, store10-bit row tag, invalidate other rows when that way changes region, and distribute shared prefix comparisons before per-row hit qualification.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        icache_removed_tag_ff_bits=128*12-24,
        icache_removed_ff_area_component_um2=(128*12-24)*.2916,
        icache_parallel_high_prefix_comparisons_before=128*3,
        icache_parallel_high_prefix_comparisons_after=2*4*3,
        icache_region_changes_can_increase_cross_region_misses=True,
        icache_region_tag_ipc_area_fmax_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_EXACT_REGION_OWNED_ICACHE_TAGS_CAPACITY_RETAINED_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,
        source_arguments=[
            'Each way stores exact PC31:20 prefix; each of64 rows stores PC19:10 low tag. Full reconstructed tag retains all22 original bits. Query set/way ownership and data array capacity128x128 are unchanged.',
            'Accepted nonerror refill updates chosen way prefix and chosen row low tag. If prefix changes, every other row of that way becomes invalid on the same edge; row fill has priority over region invalidation and reset has priority over both.',
            'Reset invalidates all rows; unreset prefix payload cannot expose a valid old row. First fill writes exact prefix/low tag together before valid, so initial prefix unknown does not require reset/data-state initialization.',
            'Three parallel query domains demand/prefetch/control share prefix equality per way/quarter-domain, then distribute three booleans to bounded row loads. Low tag compare remains per row. Raw common prefix is not directly replicated into every comparator.',
            'Data port arbitration, pending-hit SRAM capture/copy, response ownership, all MSHR clocks/promotion/generation/error/backpressure, and entire16-line full-tag instruction filter remain exact parent source.',
            'Unchanged request arbitration excludes array hit reads on an accepted refill cycle; already-read responses retain original SRAM-to-response holding copy. Prefix replacement cannot publish old row data under a new valid tag.',
            'Different code regions are supported with exact full tags; replacing a way region may evict other valid lines, increasing misses. Nominal data capacity is retained but only two1MiB regions can reside in the primary cache at once. Six perf linked texts remain in region0, static evidence only.',
            'Removes1512 net tag FF bits (1536 per-row prefix bits replaced by24 per-way bits), FF area component440.8992um2; prefix comparisons reduce384 to24 before priced distribution/new invalidation logic. Not measured total-area saving.',
            'Default region0 parameter retains original full per-row tags. No HDL build, lint, simulation, synthesis, STA, performance or unit tests. Later coverage needs three-region alternating fills, pending hits/held responses, both ways/sets, reset/refill and stale/error replies.'
        ])
    write(BASE/'A32_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
