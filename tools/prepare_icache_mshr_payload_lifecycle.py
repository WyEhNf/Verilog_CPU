"""Separate Icache MSHR validity from bounded payload ownership, no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


PAYLOAD = r'''
    localparam integer MSHR_PAYLOAD_WIDTH=32+EPOCH_WIDTH;
    wire enabled=!reset_i;
    wire demand=enabled && request_fire_i && !request_hit_i;
    wire demand_match=demand && request_match_found_i && request_match_index_i==ROW;
    wire demand_new=demand && !request_match_found_i && free_index_i==ROW;
    wire prefetch_allocate=enabled && prefetch_step_allocates_i && free_index_i==ROW;
    wire control_allocate=enabled && control_target_allocate_i && response_index_i==ROW;
    wire [2:0] pc_events={control_allocate,prefetch_allocate,demand_match || demand_new};
    wire [2:0] line_events={control_allocate,prefetch_allocate,demand_new};
    wire [3*MSHR_PAYLOAD_WIDTH-1:0] pc_values={
        current_epoch_i,control_target_i,prefetch_epoch_i,prefetch_next_line_i,if_req_epoch_i,if_req_pc_i};
    wire [3*MSHR_PAYLOAD_WIDTH-1:0] line_values={
        current_epoch_i,control_target_i[31:4],4'b0,prefetch_epoch_i,prefetch_next_line_i,if_req_epoch_i,request_line_i};
    wire pc_write,line_write;
    wire [MSHR_PAYLOAD_WIDTH-1:0] next_pc,next_line,saved_pc,saved_line;
    rv32_frequency_event_select #(.WIDTH(MSHR_PAYLOAD_WIDTH),.EVENTS(3)) pc_selector (
        .events_i(pc_events),.values_i(pc_values),.write_o(pc_write),.value_o(next_pc));
    rv32_frequency_event_select #(.WIDTH(MSHR_PAYLOAD_WIDTH),.EVENTS(3)) line_selector (
        .events_i(line_events),.values_i(line_values),.write_o(line_write),.value_o(next_line));
    rv32_frequency_word_bank #(.WIDTH(MSHR_PAYLOAD_WIDTH)) pc_owner (
        .clk_i(clk_i),.write_i(pc_write),.data_i(next_pc),.data_o(saved_pc));
    rv32_frequency_word_bank #(.WIDTH(MSHR_PAYLOAD_WIDTH)) line_owner (
        .clk_i(clk_i),.write_i(line_write),.data_i(next_line),.data_o(saved_line));
    assign {demand_epoch_o,pc_o}=saved_pc;
    assign {txn_epoch_o,line_o}=saved_line;
'''


def lifecycle(t):
    start=t.index('(* keep_hierarchy = 1 *)\nmodule rv32_icache_mshr_state_bank')
    stop=t.index('\nendmodule',start)
    bank=t[start:stop]
    bank=change(bank,'(* keep_hierarchy = 1 *)\n','')
    for field in ['pc_o','line_o','demand_epoch_o','txn_epoch_o']:
        pattern=r'output reg (\[[^\n]*?\] )'+field
        bank,n=re.subn(pattern,lambda m:'output wire '+m[1]+field,bank)
        if n!=1: raise ValueError('Missing MSHR payload '+field)
        # These are standalone assignments with no guards on the same line.
        bank,n=re.subn(r'^            *'+field+r' <= [^;]*;\n','',bank,flags=re.M)
        if n<1: raise ValueError('Missing MSHR writes '+field)
    bank=change(bank,'    always @(posedge clk_i) begin',PAYLOAD+'\n    always @(posedge clk_i) begin')
    return t[:start]+bank+t[stop:]


if __name__=='__main__':
    prepare('AQ_icache_mshr_validity_owned_payload',ROOT/'AP_prf_bounded_query_and_read',
            {'rtl/cache/rv32_icache_nonblocking.v':lifecycle},
            'AP plus MSHR PC/demand-epoch and line/transaction-epoch local bounded payload events; demand match does not change transaction identity, new demand < sequential prefetch < control prefetch; scalar validity/sent/prefetch priorities retain reset/cleanup/send/response; full allocation before valid use, no payload reset or extra FF/cycles; no EDA')
