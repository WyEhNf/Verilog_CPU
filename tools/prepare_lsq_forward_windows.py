"""Prepare bounded LSQ forward-query/byte windows; no hardware invocation."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def forward_windows(t):
    t=change(t, '''    wire [1:0] selected_size=(REQUEST_PIPELINE!=0)?selection_size:pick_size;
    wire selected_unsigned''', '''    wire [1:0] selected_size=(REQUEST_PIPELINE!=0)?selection_size:pick_size;
    // A forwarding row consumes its own address + decoded byte-mask view.
    // Raw selection FFs no longer drive every row's overlap/data formatter.
    localparam integer FORWARD_QUERY_WIDTH=36;
    wire [LSQ_ENTRIES*FORWARD_QUERY_WIDTH-1:0] forward_query_views;
    rv32_frequency_control_tree #(.WIDTH(FORWARD_QUERY_WIDTH),.LEAVES(LSQ_ENTRIES)) forward_query_tree (
        .signal_i({selected_addr,access_mask(selected_size)}),.views_o(forward_query_views));
    wire selected_unsigned''')
    t=change(t, '''            assign store_overlap[age_slot] =
                valid_mem[age_slot] && store_mem[age_slot] &&
                addr_ready_mem[age_slot] && data_ready_mem[age_slot] &&
                (CIRCULAR_ORDER_POWER2 ? older_than_selected : (entry_age[age_slot] < selected_age)) &&
                (addr_mem[age_slot][31:4] == selected_addr[31:4]) ?
                relative_overlap(addr_mem[age_slot][3:0], mask_mem[age_slot],
                    selected_addr[3:0], access_mask(selected_size)) : 4'b0;
            assign store_forward_data[age_slot] = store_data_relative_to_load(
                data_mem[age_slot], addr_mem[age_slot][3:0], mask_mem[age_slot],
                selected_addr[3:0], access_mask(selected_size));''', '''            wire [31:0] local_load_addr;
            wire [3:0] local_load_mask,local_overlap;
            assign {local_load_addr,local_load_mask}=
                forward_query_views[age_slot*FORWARD_QUERY_WIDTH +: FORWARD_QUERY_WIDTH];
            rv32_lsq_forward_window window_owner (
                .store_data_i(data_mem[age_slot]),.store_offset_i(addr_mem[age_slot][3:0]),
                .store_mask_i(mask_mem[age_slot]),.load_offset_i(local_load_addr[3:0]),
                .load_mask_i(local_load_mask),.mask_o(local_overlap),.data_o(store_forward_data[age_slot]));
            assign store_overlap[age_slot] =
                valid_mem[age_slot] && store_mem[age_slot] &&
                addr_ready_mem[age_slot] && data_ready_mem[age_slot] &&
                (CIRCULAR_ORDER_POWER2 ? older_than_selected : (entry_age[age_slot] < selected_age)) &&
                (addr_mem[age_slot][31:4] == local_load_addr[31:4]) ? local_overlap : 4'b0;''')
    return t+r'''

// Exact relative byte routing for any pair of four-bit line offsets.
// Instead of sixteen repeated (load_offset+b)==(store_offset+j) comparisons,
// decode seven possible nonempty windows once and share across the four bytes.
// This adds no state, speculation, or new alignment assumption.
(* keep_hierarchy = 1 *)
module rv32_lsq_forward_window (
    input wire [31:0] store_data_i,
    input wire [3:0] store_offset_i,store_mask_i,load_offset_i,load_mask_i,
    output wire [3:0] mask_o,
    output wire [31:0] data_o
);
    // Five bits exactly represent every difference in [-15,+15] modulo32.
    // Only differences -3..+3 can place a store byte in the four-byte window.
    wire [4:0] offset_delta={1'b0,load_offset_i}-{1'b0,store_offset_i};
    wire [6:0] alignments;
    wire [27:0] alignment_views;
    rv32_frequency_control_tree #(.WIDTH(7),.LEAVES(4)) alignment_tree (
        .signal_i(alignments),.views_o(alignment_views));
    genvar delta_id,load_byte,store_byte;
    generate
        for(delta_id=0;delta_id<7;delta_id=delta_id+1) begin:g_delta
            localparam [4:0] DELTA=delta_id-3;
            assign alignments[delta_id]=offset_delta==DELTA;
        end
        for(load_byte=0;load_byte<4;load_byte=load_byte+1) begin:g_load_byte
            wire [3:0] matches;
            wire [7:0] routed [0:3];
            for(store_byte=0;store_byte<4;store_byte=store_byte+1) begin:g_store_byte
                localparam integer ALIGNMENT=store_byte-load_byte+3;
                wire match_view;
                rv32_frequency_control_tree #(.LEAVES(1)) match_tree (
                    .signal_i(load_mask_i[load_byte] && store_mask_i[store_byte] &&
                              alignment_views[load_byte*7+ALIGNMENT]),.views_o(match_view));
                assign matches[store_byte]=match_view;
                assign routed[store_byte]={8{match_view}} & store_data_i[store_byte*8 +: 8];
            end
            // There is at most one matching source byte for each output byte.
            assign mask_o[load_byte]=|matches;
            assign data_o[load_byte*8 +: 8]=(routed[0] | routed[1]) | (routed[2] | routed[3]);
        end
    endgenerate
endmodule
'''


if __name__=='__main__':
    prepare('DF_lsq_forward_windows',ROOT/'DE_dcache_command_line',
            {'rtl/backend/rv32_lsq.v':forward_windows},
            'DE plus per-row selected load address/decoded byte-mask domains, exact shared five-bit '
            'offset-difference decoding and four bounded byte routes; same overlap/youngest-store '
            'selection and no new alignment requirement or cycle')
