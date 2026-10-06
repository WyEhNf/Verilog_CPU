"""Balanced AXI free/send/reply selection with original cursor policy."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


SELECTORS = r'''
    wire [READ_LINES-1:0] read_free_candidates,read_send_candidates,read_upper_candidates,read_reply_candidates;
    wire [WRITE_LINES-1:0] write_free_candidates,write_send_candidates,write_upper_candidates,write_reply_candidates;
    wire read_upper_found,write_upper_found;
    wire [RPW-1:0] read_upper;
    wire [WPW-1:0] write_upper;
    genvar candidate_row;
    generate
        for(candidate_row=0;candidate_row<WRITE_LINES;candidate_row=candidate_row+1) begin:g_write_candidates
            assign write_free_candidates[candidate_row]=!write_valid[candidate_row];
            assign write_send_candidates[candidate_row]=write_valid[candidate_row] && write_sent[candidate_row]<4;
            assign write_upper_candidates[candidate_row]=write_send_candidates[candidate_row] && candidate_row>=write_cursor;
            assign write_reply_candidates[candidate_row]=write_valid[candidate_row] && write_sent[candidate_row]==4 &&
                write_received[candidate_row]==write_expected[candidate_row] && d_slot_free;
        end
        for(candidate_row=0;candidate_row<READ_LINES;candidate_row=candidate_row+1) begin:g_read_candidates
            assign read_free_candidates[candidate_row]=!read_valid[candidate_row];
            assign read_send_candidates[candidate_row]=read_valid[candidate_row] && read_sent[candidate_row]<4;
            assign read_upper_candidates[candidate_row]=read_send_candidates[candidate_row] && candidate_row>=read_cursor;
            assign read_reply_candidates[candidate_row]=read_valid[candidate_row] && read_received[candidate_row]==4 &&
                (read_data_side[candidate_row]?(d_slot_free && !(write_reply_found && prefer_write_reply)):i_slot_free);
        end
    endgenerate
    rv32_frequency_first_two #(.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_free_selector (
        .candidates_i(read_free_candidates),.first_valid_o(read_free_found),.first_index_o(read_free),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_free_selector (
        .candidates_i(write_free_candidates),.first_valid_o(write_free_found),.first_index_o(write_free),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_wrap_selector (
        .candidates_i(read_send_candidates),.first_valid_o(read_wrap_found),.first_index_o(read_wrap),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_upper_selector (
        .candidates_i(read_upper_candidates),.first_valid_o(read_upper_found),.first_index_o(read_upper),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_wrap_selector (
        .candidates_i(write_send_candidates),.first_valid_o(write_wrap_found),.first_index_o(write_wrap),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_upper_selector (
        .candidates_i(write_upper_candidates),.first_valid_o(write_upper_found),.first_index_o(write_upper),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_reply_selector (
        .candidates_i(read_reply_candidates),.first_valid_o(read_reply_found),.first_index_o(read_reply),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_reply_selector (
        .candidates_i(write_reply_candidates),.first_valid_o(write_reply_found),.first_index_o(write_reply),
        .second_valid_o(),.second_index_o());
    assign read_send_found=read_upper_found || read_wrap_found;
    assign read_send=read_upper_found?read_upper:read_wrap;
    assign write_send_found=write_upper_found || write_wrap_found;
    assign write_send=write_upper_found?write_upper:write_wrap;
'''


def arbitration(t):
    t=change(t,'    integer scan;\n','')
    t=change(t,'    integer read_free, write_free, read_send, write_send, read_reply, write_reply;',
               '    wire [RPW-1:0] read_free,read_send,read_reply;\n    wire [WPW-1:0] write_free,write_send,write_reply;')
    t=change(t,'    integer read_wrap, write_wrap;',
               '    wire [RPW-1:0] read_wrap;\n    wire [WPW-1:0] write_wrap;')
    for d in ['read_free_found, write_free_found, read_send_found, write_send_found',
              'read_reply_found, write_reply_found','read_wrap_found, write_wrap_found']:
        t=change(t,'    reg '+d+';','    wire '+d+';')
    a=t.index('    always @* begin\n        read_free =')
    b=t.index('    wire d_read_request',a)
    return t[:a]+SELECTORS+'\n'+t[b:]


if __name__=='__main__':
    prepare('BL_axi_balanced_cursor_arbitration',ROOT/'BK1_axi_row_lifecycle',
            {'rtl/course/rv32_axi_lite_bridge.v':arbitration},
            'BK1 plus parallel per-row AXI candidates and binary free/send/reply priority; sender selects first eligible at/above cursor then lowest wrap, reply retains write preference and independent I/D capacity qualification; bounded indices, no added FF/cycles and no EDA')
