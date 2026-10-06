"""Split Dcache MSHR payload ownership at unchanged edges; no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    // Allocation initializes every field before mshr_valid exposes it. A
    // promoted prefetch replaces only the demand descriptor; masked store
    // merging retains all older bytes. Lifecycle validity remains separate.
    localparam integer MSHR_PAYLOAD_DOMAINS=(MSHR_ENTRIES+3)/4;
    localparam integer MSHR_DEMAND_WIDTH=TAG_WIDTH+35;
    localparam integer MSHR_VICTIM_WIDTH=CACHE_ENTRY_WIDTH+32;
    localparam integer MSHR_ACTION_WIDTH=17;
    wire [MSHR_PAYLOAD_DOMAINS*MSHR_ACTION_WIDTH-1:0] mshr_action_views;
    rv32_frequency_control_tree #(.WIDTH(MSHR_ACTION_WIDTH),.LEAVES(MSHR_PAYLOAD_DOMAINS)) mshr_action_tree (
        .signal_i({reset_i,static_prefetch_allocate,victim_from_sram,
                   second_free_index[2:0],free_index[2:0],matching_index[2:0],static_request_action}),
        .views_o(mshr_action_views));
    genvar payload_mshr;
    generate for(payload_mshr=0;payload_mshr<MSHR_ENTRIES;payload_mshr=payload_mshr+1) begin:g_mshr_payload_owner
        wire local_reset,prefetch_allocate,victim_copy;
        wire [2:0] second_slot,free_slot,matching_slot;
        wire [3:0] action;
        assign {local_reset,prefetch_allocate,victim_copy,second_slot,free_slot,matching_slot,action}=
            mshr_action_views[(payload_mshr/4)*MSHR_ACTION_WIDTH +: MSHR_ACTION_WIDTH];
        wire load_promote=!local_reset && action==4'd4 && matching_slot==payload_mshr;
        wire store_promote=!local_reset && action==4'd6 && matching_slot==payload_mshr;
        wire store_merge=!local_reset && action==4'd7 && matching_slot==payload_mshr;
        wire demand_allocate=!local_reset && action==4'd8 && free_slot==payload_mshr;
        wire prefetch_new=!local_reset && prefetch_allocate && second_slot==payload_mshr;
        wire demand_write;
        wire [MSHR_DEMAND_WIDTH-1:0] demand_next,demand_saved;
        rv32_frequency_event_select #(.WIDTH(MSHR_DEMAND_WIDTH),.EVENTS(4)) demand_selector (
            .events_i({prefetch_new,demand_allocate,store_promote,load_promote}),
            .values_i({
                {TAG_WIDTH{1'b0}},1'b1,`RV32IM_MEM_WORD,prefetch_line_addr,
                core_req_lsq_tag,core_req_unsigned,core_req_size,core_req_addr,
                core_req_lsq_tag,1'b0,core_req_size,core_req_addr,
                core_req_lsq_tag,core_req_unsigned,core_req_size,core_req_addr}),
            .write_o(demand_write),.value_o(demand_next));
        rv32_frequency_word_bank #(.WIDTH(MSHR_DEMAND_WIDTH)) demand_owner (
            .clk_i(clk_i),.write_i(demand_write),.data_i(demand_next),.data_o(demand_saved));
        assign {mshr_lsq[payload_mshr],mshr_unsigned[payload_mshr],
                mshr_size[payload_mshr],mshr_addr[payload_mshr]}=demand_saved;

        wire mask_write;
        wire [15:0] mask_next;
        rv32_frequency_event_select #(.WIDTH(16),.EVENTS(4)) mask_selector (
            .events_i({prefetch_new,demand_allocate,store_merge,store_promote}),
            .values_i({16'b0,(request_is_store?core_req_mask:16'b0),
                       (mshr_mask[payload_mshr] | core_req_mask),core_req_mask}),
            .write_o(mask_write),.value_o(mask_next));
        rv32_frequency_word_bank #(.WIDTH(16)) mask_owner (
            .clk_i(clk_i),.write_i(mask_write),.data_i(mask_next),.data_o(mshr_mask[payload_mshr]));

        wire victim_write;
        wire [MSHR_VICTIM_WIDTH-1:0] victim_next,victim_saved;
        rv32_frequency_event_select #(.WIDTH(MSHR_VICTIM_WIDTH),.EVENTS(2)) victim_selector (
            .events_i({prefetch_new,demand_allocate}),
            .values_i({prefetch_victim_entry,32'b0,request_victim_entry,
                victim_line_address(request_tags[(request_victim_entry%CACHE_WAYS)*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH],request_index)}),
            .write_o(victim_write),.value_o(victim_next));
        rv32_frequency_word_bank #(.WIDTH(MSHR_VICTIM_WIDTH)) victim_owner (
            .clk_i(clk_i),.write_i(victim_write),.data_i(victim_next),.data_o(victim_saved));
        assign {mshr_victim_entry[payload_mshr],mshr_victim_addr[payload_mshr]}=victim_saved;

        // Deferred synchronous SRAM capture precedes new allocation in the
        // original process. New demand/prefetch allocation wins on collision.
        wire victim_data_write;
        wire [127:0] victim_data_next;
        wire deferred_capture=!local_reset && victim_copy && victim_mshr_reg==payload_mshr;
        wire [127:0] allocated_victim=(request_dirty_victim && TAG_SRAM!=0)?data_rdata:128'b0;
        rv32_frequency_event_select #(.WIDTH(128),.EVENTS(3)) victim_data_selector (
            .events_i({prefetch_new,demand_allocate,deferred_capture}),
            .values_i({128'b0,allocated_victim,data_rdata}),
            .write_o(victim_data_write),.value_o(victim_data_next));
        rv32_frequency_word_bank #(.WIDTH(128)) victim_data_owner (
            .clk_i(clk_i),.write_i(victim_data_write),.data_i(victim_data_next),.data_o(mshr_victim_data[payload_mshr]));
    end endgenerate
'''


def owners(t):
    fields=['mshr_addr','mshr_size','mshr_unsigned','mshr_mask','mshr_lsq',
            'mshr_victim_addr','mshr_victim_data','mshr_victim_entry']
    for field in fields:
        pattern=r'^    reg (\[[^\n]*?\] )?'+field+r' \[0:MSHR_ENTRIES-1\];'
        t,n=re.subn(pattern,lambda m:'    wire '+(m[1] or '')+field+' [0:MSHR_ENTRIES-1];',t,flags=re.M)
        if n!=1: raise ValueError('Expected declaration '+field)
    t=change(t,'            if (victim_from_sram)\n                mshr_victim_data[victim_mshr_reg] <= data_rdata;\n','')
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            resp_valid_reg')
    stop=t.index('\n    initial begin',start)
    commands=t[start:stop]
    for field in fields:
        pattern=r'^ +'+field+r'\[[^\n]*?\]\s*<=\s*[^;]*;\n'
        commands,n=re.subn(pattern,'',commands,flags=re.M)
        if n<2 or re.search(r'^ +'+field+r'\[[^\]\n]*\]\s*<=',commands,flags=re.M):
            raise ValueError('Review residual MSHR writes '+field)
    # The TAG_SRAM!=0 victim-data branch now belongs entirely to its owner.
    commands=change(commands,'                        end else begin\n                        end\n','                        end\n')
    return t[:start]+OWNERS+'\n'+commands+t[stop:]


if __name__=='__main__':
    prepare('AZ1_dcache_mshr_payload_owners',ROOT/'AY_bounded_backend_map_queries',
            {'rtl/cache/rv32_dcache_nonblocking.v':owners},
            'AY plus Dcache MSHR demand/mask/victim descriptor and 128-bit victim data local event owners, four-row action domains and sixteen-bit select/write leaves; preserve promote/merge/allocate and deferred SRAM capture priorities, no payload reset when invalid, scalar lifecycle unchanged; no added FF/cycles and no EDA')
