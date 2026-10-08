`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Physical register file for the rename/issue boundary.
//
// Ports are flattened in lane order: lane n occupies the slice beginning at
// n*width.  A write in the highest numbered lane wins when multiple valid
// writes target the same physical register in one cycle.
module rv32_physical_register_file #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer READ_MUX_IMPL = 0,
    parameter integer LOCAL_VALUE_ROWS = 0,
    parameter integer VALUE_SRAM = 0,
    parameter integer SRAM_PORT_FORWARD = 0,
    parameter integer SRAM_RAW_WRITE = 0,
    // Optional combination output for even allocation read ports only.
    // The original read data/ready and storage updates remain independent.
    parameter STORE_ADDRESS_READ = 0,
    // Optional ram/half/word alignment flags computed before the same
    // stored/write-through address event selector. No state or edge added.
    parameter STORE_ADDRESS_FLAGS = 0,
    // Private saved-operand qualification; never changes public read data.
    parameter STORE_SAVED_QUERY = 0,
    parameter STORE_CLASS_COMPARE = 0,
    parameter integer PHYS_ADDR_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire [(2*BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] read_phys_i,
    output reg  [(2*BE_WIDTH*32)-1:0]   read_data_o,
    output reg  [(2*BE_WIDTH)-1:0]      read_ready_o,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] alloc_phys_i,
    input  wire [BE_WIDTH-1:0]           alloc_valid_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] write_phys_i,
    input  wire [(BE_WIDTH*32)-1:0]      write_data_i,
    input  wire [BE_WIDTH-1:0]           write_valid_i,
    input  wire [BE_WIDTH*12-1:0]        store_offset_i,
    output wire [BE_WIDTH*32-1:0]       store_address_o,
    output wire [BE_WIDTH*3-1:0]        store_address_flags_o,
    output wire [2*BE_WIDTH-1:0]       read_stored_ready_o,
    output wire [2*BE_WIDTH-1:0]       read_bypass_pending_o,
    output wire [BE_WIDTH*3-1:0]       store_saved_flags_o
);
    // Keep the value store as a word array so synthesis can implement it as
    // a compact multi-ported memory.  The previous flattened vector forced
    // every data bit into a flip-flop plus a large read mux.
    wire [31:0] value [0:PHYS_REGS-1];

    wire [PHYS_REGS-1:0] ready;

    initial begin
        if((SRAM_RAW_WRITE!=0 && SRAM_RAW_WRITE!=1) || (SRAM_RAW_WRITE!=0 && (VALUE_SRAM==0 || LOCAL_VALUE_ROWS==0)))
            $fatal(1,"Raw SRAM write data requires local SRAM rows");
        if((SRAM_PORT_FORWARD!=0 && SRAM_PORT_FORWARD!=1) ||
           (SRAM_PORT_FORWARD!=0 && (VALUE_SRAM==0 || LOCAL_VALUE_ROWS==0 || READ_MUX_IMPL==0)))
            $fatal(1,"SRAM port forwarding requires SRAM/local/parallel read policy");
        if ((VALUE_SRAM!=0 && VALUE_SRAM!=1) || (VALUE_SRAM!=0 && LOCAL_VALUE_ROWS==0)) begin
            $display("ERROR: SRAM values require local PRF row ownership");
            $finish(1);
        end
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid PRF BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if (PHYS_REGS < 33) begin
            $display("ERROR: invalid PRF PHYS_REGS=%0d; expected at least 33", PHYS_REGS);
            $finish;
        end
        if (PHYS_ADDR_WIDTH < $clog2(PHYS_REGS)) begin
            $display("ERROR: invalid PRF PHYS_ADDR_WIDTH=%0d for PHYS_REGS=%0d", PHYS_ADDR_WIDTH, PHYS_REGS);
            $finish;
        end
    end

    localparam integer READ_DOMAINS=4;
    wire [2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_phys_local;
    wire [READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_domain_queries;
    wire unused_read_domain_queries_bits = &{1'b0, read_domain_queries};

    generate if(READ_MUX_IMPL!=0) begin:g_query_domains
        wire [(READ_DOMAINS+1)*2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] queries;
        rv32_frequency_control_tree #(.WIDTH(2*BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(READ_DOMAINS+1)) query_tree (
            .signal_i(read_phys_i),.views_o(queries));
        assign read_domain_queries=queries[0 +: READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH];
        assign read_phys_local=queries[READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH +: 2*BE_WIDTH*PHYS_ADDR_WIDTH];
    end else begin:g_legacy_query
        rv32_frequency_control_tree #(.WIDTH(2*BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(1)) query_tree (
            .signal_i(read_phys_i),.views_o(read_phys_local));
        assign read_domain_queries=0;
    end endgenerate
    wire [4*BE_WIDTH-1:0] recent_valids;
    wire [4*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] recent_addresses;
    wire [4*BE_WIDTH*32-1:0] recent_values;
    generate if(VALUE_SRAM!=0) begin:g_recent_writeback
        reg [BE_WIDTH-1:0] previous_valid;
        wire [BE_WIDTH*PHYS_ADDR_WIDTH-1:0] previous_ids;
        wire [BE_WIDTH*32-1:0] previous_values;
        always @(posedge clk_i)
            if(reset_i) previous_valid<=0;
            else previous_valid<=write_valid_i;
        rv32_frequency_word_bank #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH)) id_capture (
            .clk_i(clk_i),.write_i(!reset_i && |write_valid_i),
            .data_i(write_phys_i),.data_o(previous_ids));
        rv32_frequency_word_bank #(.WIDTH(BE_WIDTH*32)) value_capture (
            .clk_i(clk_i),.write_i(!reset_i && |write_valid_i),
            .data_i(write_data_i),.data_o(previous_values));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) valid_tree (
            .signal_i(previous_valid),.views_o(recent_valids));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) id_tree (
            .signal_i(previous_ids),.views_o(recent_addresses));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*32),.LEAVES(4)) value_tree (
            .signal_i(previous_values),.views_o(recent_values));
    end else begin:g_no_recent_writeback
        assign recent_valids=0;assign recent_addresses=0;assign recent_values=0;
    end endgenerate
    genvar owner_row,owner_lane;
    generate if(LOCAL_VALUE_ROWS!=0) begin:g_local_storage
`ifdef CPU2026_WORD_SIM
        if(VALUE_SRAM==0 && PHYS_REGS==56 && PHYS_ADDR_WIDTH==6 &&
           (BE_WIDTH==1 || BE_WIDTH==2 || BE_WIDTH==4)) begin:g_word_storage
            reg [31:0] words [0:55];
            reg [55:0] word_ready;
            wire unused_word_ready_bits = &{1'b0, word_ready};

            integer lane;
            for(owner_row=0;owner_row<56;owner_row=owner_row+1) begin:g_view
                assign value[owner_row]=(owner_row==0)?32'b0:words[owner_row];
            end
            assign ready={word_ready[55:1],1'b1};
            always @(posedge clk_i) begin
                if(reset_i) word_ready<=56'b1;
                else begin
                    for(lane=0;lane<BE_WIDTH;lane=lane+1)
                        if(alloc_valid_i[lane] && alloc_phys_i[lane*6+:6]!=0 && alloc_phys_i[lane*6+:6]<56)
                            word_ready[alloc_phys_i[lane*6+:6]]<=1'b0;
                    // Write-through completion wins over allocation, and
                    // the highest numbered write lane wins duplicate writes.
                    for(lane=0;lane<BE_WIDTH;lane=lane+1)
                        if(write_valid_i[lane] && write_phys_i[lane*6+:6]!=0 && write_phys_i[lane*6+:6]<56) begin
                            words[write_phys_i[lane*6+:6]]<=write_data_i[lane*32+:32];
                            word_ready[write_phys_i[lane*6+:6]]<=1'b1;
                        end
                end
            end
        end else begin:g_original_storage
`endif

        wire [PHYS_REGS-1:0] reset_views;
        rv32_frequency_control_tree #(.LEAVES(PHYS_REGS)) reset_tree (
            .signal_i(reset_i),.views_o(reset_views));
        wire [4*BE_WIDTH*32-1:0] write_values;
        wire [4*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] write_addresses,alloc_addresses;
        wire [4*BE_WIDTH-1:0] write_valids,alloc_valids;
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*32),.LEAVES(4)) value_tree (
            .signal_i(write_data_i),.views_o(write_values));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) write_address_tree (
            .signal_i(write_phys_i),.views_o(write_addresses));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) alloc_address_tree (
            .signal_i(alloc_phys_i),.views_o(alloc_addresses));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) write_valid_tree (
            .signal_i(write_valid_i),.views_o(write_valids));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) alloc_valid_tree (
            .signal_i(alloc_valid_i),.views_o(alloc_valids));
        for(owner_row=0;owner_row<PHYS_REGS;owner_row=owner_row+1) begin:g_row
            if(owner_row==0) begin:g_zero
                assign value[owner_row]=0;assign ready[owner_row]=1;
            end else begin:g_register
                localparam integer DOMAIN=(owner_row*4)/PHYS_REGS;
                wire [BE_WIDTH-1:0] writes,allocations,recent_matches;
                for(owner_lane=0;owner_lane<BE_WIDTH;owner_lane=owner_lane+1) begin:g_match
                    assign writes[owner_lane]=write_valids[DOMAIN*BE_WIDTH+owner_lane] &&
                        write_addresses[(DOMAIN*BE_WIDTH+owner_lane)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==owner_row;
                    assign allocations[owner_lane]=alloc_valids[DOMAIN*BE_WIDTH+owner_lane] &&
                        alloc_addresses[(DOMAIN*BE_WIDTH+owner_lane)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==owner_row;
                    assign recent_matches[owner_lane]=recent_valids[DOMAIN*BE_WIDTH+owner_lane] &&
                        recent_addresses[(DOMAIN*BE_WIDTH+owner_lane)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==owner_row;
                end
                rv32_prf_value_row #(.LANES(BE_WIDTH),.VALUE_SRAM(VALUE_SRAM),.RAW_SRAM_OUTPUT(SRAM_PORT_FORWARD),.RAW_SRAM_WRITE(SRAM_RAW_WRITE)) contents (
                    .clk_i(clk_i),.reset_i(reset_views[owner_row]),.alloc_i(|allocations),.write_matches_i(writes),
                    .write_values_i(write_values[DOMAIN*BE_WIDTH*32 +: BE_WIDTH*32]),
                    .recent_matches_i(recent_matches),.recent_values_i(recent_values[DOMAIN*BE_WIDTH*32 +: BE_WIDTH*32]),
                    .value_o(value[owner_row]),.ready_o(ready[owner_row]));
            end
        end
`ifdef CPU2026_WORD_SIM
        end
`endif
    end else begin:g_legacy_alias
        for(owner_row=0;owner_row<PHYS_REGS;owner_row=owner_row+1) begin:g_row
            assign value[owner_row]=g_legacy_storage.value_legacy[owner_row];
        end

        assign ready=g_legacy_storage.ready_legacy;
    end endgenerate

    // Four query domains decode physical words independently. Data and ready
    // use separate bounded select leaves; the reductions have explicit depth.
    localparam integer READ_ROWS=(PHYS_REGS<=1)?1:(1<<$clog2(PHYS_REGS));
    genvar rp,row,wl,read_node;
    generate if(READ_MUX_IMPL!=0) begin:g_parallel_read
        for(rp=0;rp<2*BE_WIDTH;rp=rp+1) begin:g_port
            wire [PHYS_ADDR_WIDTH-1:0] address=read_phys_local[rp*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
            wire legal=address!=0 && 32'(address)<PHYS_REGS;
            wire [31:0] stored_tree [1:2*READ_ROWS-1];
            wire ready_tree [1:2*READ_ROWS-1];
            wire [BE_WIDTH-1:0] bypass_match;
            wire [31:0] bypass_value;
            wire bypass_write;
            wire [1:0] bypass_select;
`ifdef CPU2026_WORD_SIM
            if(PHYS_REGS==56 && PHYS_ADDR_WIDTH==6) begin:g_word_read
                assign stored_tree[1]=legal ? value[address] : 32'b0;
                assign ready_tree[1]=legal && ready[address];
            end else begin:g_original_read
`endif
            for(row=0;row<READ_ROWS;row=row+1) begin:g_word
                if(row>0 && row<PHYS_REGS) begin:g_present
                    localparam integer DOMAIN=(row*READ_DOMAINS)/PHYS_REGS;
                    wire selected=read_domain_queries[(DOMAIN*2*BE_WIDTH+rp)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==row;
                    wire [2:0] select_views;
                    rv32_frequency_control_tree #(.LEAVES(3)) selection_tree (
                        .signal_i(selected),.views_o(select_views));
                    assign stored_tree[READ_ROWS+row]={{16{select_views[1]}} & value[row][31:16],{16{select_views[0]}} & value[row][15:0]};
                    assign ready_tree[READ_ROWS+row]=select_views[2] && ready[row];
                end else begin:g_zero_or_padding
                    assign stored_tree[READ_ROWS+row]=0;
                    assign ready_tree[READ_ROWS+row]=0;
                end
            end
            for(read_node=1;read_node<READ_ROWS;read_node=read_node+1) begin:g_reduce
                assign stored_tree[read_node]=stored_tree[2*read_node] | stored_tree[2*read_node+1];
                assign ready_tree[read_node]=ready_tree[2*read_node] | ready_tree[2*read_node+1];
            end
`ifdef CPU2026_WORD_SIM
            end
`endif
            wire [31:0] stored_value;
            if(SRAM_PORT_FORWARD!=0) begin:g_recent_port
                localparam integer DOMAIN=(rp*READ_DOMAINS)/(2*BE_WIDTH);
                wire [BE_WIDTH-1:0] previous_matches;
                wire [31:0] previous_value;
                wire previous_write;
                wire [1:0] previous_select;
                for(genvar recent_lane=0;recent_lane<BE_WIDTH;recent_lane=recent_lane+1) begin:g_match
                    assign previous_matches[recent_lane]=legal && recent_valids[DOMAIN*BE_WIDTH+recent_lane] &&
                        recent_addresses[(DOMAIN*BE_WIDTH+recent_lane)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==address;
                end
                rv32_frequency_event_select #(.WIDTH(32),.EVENTS(BE_WIDTH)) previous_selector (
                    .events_i(previous_matches),.values_i(recent_values[DOMAIN*BE_WIDTH*32 +: BE_WIDTH*32]),
                    .write_o(previous_write),.value_o(previous_value));
                rv32_frequency_control_tree #(.LEAVES(2)) previous_choice_tree (
                    .signal_i(previous_write),.views_o(previous_select));
                assign stored_value={previous_select[1]?previous_value[31:16]:stored_tree[1][31:16],
                                     previous_select[0]?previous_value[15:0]:stored_tree[1][15:0]};
            end else begin:g_recent_row
                assign stored_value=stored_tree[1];
            end
            for(wl=0;wl<BE_WIDTH;wl=wl+1) begin:g_bypass
                assign bypass_match[wl]=legal && write_valid_i[wl] &&
                    write_phys_i[wl*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==address;
            end
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(BE_WIDTH)) bypass_selector (
                .events_i(bypass_match),.values_i(write_data_i),.write_o(bypass_write),.value_o(bypass_value));
            rv32_frequency_control_tree #(.LEAVES(2)) bypass_choice_tree (
                .signal_i(bypass_write),.views_o(bypass_select));
            if(STORE_SAVED_QUERY!=0) begin:g_saved_operand_query
                assign read_stored_ready_o[rp]=(address==0) || ready_tree[1];
                assign read_bypass_pending_o[rp]=bypass_write;
            end else begin:g_no_saved_operand_query
                assign read_stored_ready_o[rp]=1'b0;
                assign read_bypass_pending_o[rp]=1'b0;
            end
            if((rp%2)==0) begin:g_store_address_output
                if(STORE_ADDRESS_READ!=0) begin:g_parallel_calculation
                    wire [BE_WIDTH:0] address_events;
                    wire [(BE_WIDTH+1)*32-1:0] address_values;
                    // The fallback is the SAME un-bypassed read-tree value.
                    // P0 and out-of-range rows already read zero from this tree.
                    assign address_events[0]=!bypass_write;
                    wire [2:0] stored_class_flags;
                    rv32_frequency_add_simm12 #(.CLASS_COMPARE(STORE_CLASS_COMPARE)) stored_address (
                        .base_i(stored_value),
                        .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                        .sum_o(address_values[0 +: 32]),.class_flags_o(stored_class_flags));
                    if(STORE_SAVED_QUERY!=0) begin:g_saved_address_flags
                        if(STORE_CLASS_COMPARE!=0) begin:g_direct_class
                            assign store_saved_flags_o[(rp/2)*3 +: 3]=stored_class_flags;
                        end else begin:g_original_class
                            wire [31:0] saved_address=address_values[0 +: 32];
                            assign store_saved_flags_o[(rp/2)*3 +: 3]={
                                saved_address[1:0]==2'b00,!saved_address[0],
                                saved_address[31:28]==4'b0000};
                        end
                    end else begin:g_no_saved_address_flags
                        assign store_saved_flags_o[(rp/2)*3 +: 3]=0;
                    end
                    for(genvar address_lane=0;address_lane<BE_WIDTH;address_lane=address_lane+1) begin:g_write_address
                        // Reuse legal/write-valid/phys equality. Highest write
                        // lane still wins, including the branch-link lane.
                        assign address_events[address_lane+1]=bypass_match[address_lane];
                        wire [2:0] unused_write_address_class_flags_o;
                        rv32_frequency_add_simm12 write_address (
                            .base_i(write_data_i[address_lane*32 +: 32]),
                            .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                            .sum_o(address_values[(address_lane+1)*32 +: 32]), .class_flags_o(unused_write_address_class_flags_o));
                    end
                    wire  unused_address_selector_write_o;
                    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(BE_WIDTH+1),.PRIORITY(1)) address_selector (
                        .events_i(address_events),.values_i(address_values),.write_o(unused_address_selector_write_o),
                        .value_o(store_address_o[(rp/2)*32 +: 32]));
                    if(STORE_ADDRESS_FLAGS!=0) begin:g_address_flags
                        wire [(BE_WIDTH+1)*3-1:0] flag_values;
                        for(genvar flag_lane=0;flag_lane<BE_WIDTH+1;flag_lane=flag_lane+1) begin:g_candidate
                            wire [31:0] candidate_address=address_values[flag_lane*32 +: 32];
                            wire unused_candidate_address_bits = &{1'b0, candidate_address};

                            // bit0: ordinary RAM; bit1: half alignment;
                            // bit2: word alignment. All wrap/carry is already
                            // included by the exact original address adder.
                            assign flag_values[flag_lane*3 +: 3]={
                                candidate_address[1:0]==2'b00,
                                !candidate_address[0],candidate_address[31:28]==4'b0000};
                        end
                        wire  unused_flags_selector_write_o;
                        rv32_frequency_event_select #(.WIDTH(3),.EVENTS(BE_WIDTH+1),.PRIORITY(1)) flags_selector (
                            .events_i(address_events),.values_i(flag_values),.write_o(unused_flags_selector_write_o),
                            .value_o(store_address_flags_o[(rp/2)*3 +: 3]));
                    end else begin:g_no_address_flags
                        assign store_address_flags_o[(rp/2)*3 +: 3]=0;
                    end
                end else begin:g_disabled
                    assign store_address_o[(rp/2)*32 +: 32]=0;
                    assign store_address_flags_o[(rp/2)*3 +: 3]=0;
                    assign store_saved_flags_o[(rp/2)*3 +: 3]=0;
                end
            end
            always @* begin
                read_data_o[rp*32 +: 32]={bypass_select[1]?bypass_value[31:16]:stored_value[31:16],bypass_select[0]?bypass_value[15:0]:stored_value[15:0]};
                read_ready_o[rp]=(address==0) || ready_tree[1] || bypass_write;
            end
        end
    end else begin : g_original_read
    // The backend only selects this extra output with parallel read enabled.
    assign store_address_o=0;
    assign store_address_flags_o=0;
    assign read_stored_ready_o=0;
    assign read_bypass_pending_o=0;
    assign store_saved_flags_o=0;
    // Reads are combinational.  Each generated process has constant output
    // slices; @* also expands the word-array dependency for simulators.
    genvar read_port;
        for (read_port = 0; read_port < (2*BE_WIDTH); read_port = read_port + 1) begin : g_read_port
            integer bypass_lane;
            always @* begin
                bypass_lane = 0;
                read_data_o[(read_port*32) +: 32] = 32'b0;
                read_ready_o[read_port] = 1'b0;
                if (read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] == 0) begin
                    read_ready_o[read_port] = 1'b1;
                end else if (read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] < PHYS_REGS) begin
                    read_data_o[(read_port*32) +: 32] = value[read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]];
                    read_ready_o[read_port] = ready[read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]];
                    // When ready is low this data is architecturally don't-care;
                    // consumers must wait for writeback rather than depend on a
                    // reset value in the data array.
                    for (bypass_lane = 0; bypass_lane < BE_WIDTH; bypass_lane = bypass_lane + 1) begin
                        if (write_valid_i[bypass_lane] &&
                            (write_phys_i[(bypass_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] ==
                             read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH])) begin
                            read_data_o[(read_port*32) +: 32] = write_data_i[(bypass_lane*32) +: 32];
                            read_ready_o[read_port] = 1'b1;
                        end
                    end
                end
            end
        end

    end endgenerate

    generate if(LOCAL_VALUE_ROWS==0) begin:g_legacy_storage
    reg [31:0] value_legacy [0:PHYS_REGS-1];
    reg [PHYS_REGS-1:0] ready_legacy;
    integer alloc_lane;
    integer write_lane;

    always @(posedge clk_i) begin
        if (reset_i) begin
            ready_legacy <= {{(PHYS_REGS-1){1'b0}}, 1'b1};
        end else begin
            // Rename allocation makes a destination unavailable.  Writeback
            // is processed afterwards and therefore has higher priority.
            for (alloc_lane = 0; alloc_lane < BE_WIDTH; alloc_lane = alloc_lane + 1) begin
                if (alloc_valid_i[alloc_lane] &&
                    (alloc_phys_i[(alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] != 0) &&
                    (alloc_phys_i[(alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] < PHYS_REGS)) begin
                    ready_legacy[alloc_phys_i[(alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b0;
                end
            end
            // Iterating low-to-high makes the highest lane deterministic.
            // P0 is hardwired and out-of-range encoded addresses are ignored.
            for (write_lane = 0; write_lane < BE_WIDTH; write_lane = write_lane + 1) begin
                if (write_valid_i[write_lane] &&
                    (write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] != 0) &&
                    (write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] < PHYS_REGS)) begin
                    value_legacy[write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= write_data_i[(write_lane*32) +: 32];
                    ready_legacy[write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b1;
                end
            end
            ready_legacy[0] <= 1'b1;
        end
    end
    end endgenerate
endmodule
