`timescale 1ns/1ps
module rv32_lsq_mmio_admission_fixture #(parameter integer EARLY=0)(output reg done=0);
    reg clk=0,reset=1,recovery=0;
    reg load_ready=0;reg [1:0] updates=0;reg [15:0] update_tag=0;reg [31:0] update_data=0;reg allocation_data_ready=1;reg [15:0] tickets[0:3];integer row;reg [15:0] reused_ticket;
    reg monitor_loads=1;wire saved_mmio_class,admitted_mmio;
    wire original_mmio_class=request_valid && request_store && request_addr==32'h80000000 && request_mask==16'h000f;
    wire mmio_class=saved_mmio_class;
    wire routed_mmio=(EARLY!=0) ? admitted_mmio : (request_valid && mmio_class);reg [15:0] exit_ticket;integer limit;
    always #5 clk=~clk;
    reg [1:0] alloc_valid=0;
    reg [31:0] alloc_rob=0;
    reg [3:0] alloc_size=0;
    reg [63:0] alloc_addr=0,alloc_data=0;
    reg commit_valid=0,request_ready=0,ack_valid=0;
    reg [15:0] commit_tag=0,ack_tag=0;
    wire alloc_ready,commit_ready,request_valid,request_store,store_ack_valid;
    wire [31:0] alloc_tag,request_addr;
    wire [15:0] request_tag,request_mask;
    wire [127:0] request_data;
    reg [1:0] loads=0,stores=0,unsigned_load=0;
    reg response_valid=0;
    reg [15:0] response_tag=0;
    reg [31:0] response_data=0;
    wire load_valid,load_error;
    wire [31:0] load_value;
    wire [15:0] load_rob_tag;
    wire [5:0] selected_phys;
    wire [2:0] occupancy;
    integer requests=0;
    reg [15:0] ticket;
    reg [31:0] expected_addr;
    reg [127:0] expected_data;
    reg [15:0] expected_mask;
    rv32_lsq #(.PHASED_DATA_OWNER(1),.RELEASE_CREDITS(2),.SAVED_REQUEST_QUERY(1),.ALLOC_LOAD_REQUEST_BYPASS(1),.ALLOC_LOAD_SELECTION_BYPASS(1), .BE_WIDTH(2),.LSQ_ENTRIES(4),.ROB_ENTRIES(8),.TAG_WIDTH(16),.ROB_TAG_WIDTH(16),
        .REQUEST_PIPELINE(1),.EMPTY_SELECTION_BYPASS(2),.PICK_LOCAL_VALIDITY(1),
        .STORE_ADMISSION_BYPASS(1),.COMMITTED_STORE_BYPASS(1)) dut (
        .clk_i(clk),
        .reset_i(reset),
        .flush_i('0),
        .recovery_valid_i(recovery),
        .recovery_tag_i(16'h41),
        .recovery_head_i('0),
        .recovery_occupancy_i(16'd8),
        .retire_valid_i('0),
        .retire_rob_tag_i('0),
        .alloc_valid_i(alloc_valid),
        .alloc_plan_valid_i(alloc_valid),
        .alloc_is_load_i(loads),
        .alloc_is_store_i(stores),
        .alloc_rob_tag_i(alloc_rob),
        .alloc_phys_rd_i(12'd9),
        .alloc_size_i(alloc_size),
        .alloc_unsigned_i(unsigned_load),
        .alloc_addr_valid_i(alloc_valid),
        .alloc_addr_i(alloc_addr),
        .alloc_data_valid_i(alloc_valid & {2{allocation_data_ready}}),
        .alloc_store_data_i(alloc_data),
        .alloc_store_mask_i('0),
        .early_addr_valid_i('0),
        .early_addr_tag_i('0),
        .early_addr_i('0),
        .addr_update_valid_i('0),
        .addr_update_tag_i('0),
        .addr_update_i('0),
        .data_update_valid_i(updates),
        .data_update_tag_i({16'b0,update_tag}),
        .data_update_i({32'b0,update_data}),
        .data_mask_update_i('0),
        .wakeup_valid_i('0),
        .wakeup_tag_i('0),
        .wakeup_value_i('0),
        .store_commit_valid_i(commit_valid),
        .store_commit_rob_tag_i(commit_tag),
        .dcache_req_ready_i(request_ready),
        .dcache_resp_valid_i(response_valid),
        .dcache_resp_lsq_tag_i(response_tag),
        .dcache_resp_query_valid_i('0),
        .dcache_resp_query_tags_i('0),
        .dcache_resp_addr_i('0),
        .dcache_resp_line_data_i('0),
        .dcache_resp_word_data_i(response_data),
        .dcache_resp_line_valid_i('0),
        .dcache_resp_error_i('0),
        .load_complete_ready_i(load_ready),
        .dcache_store_ack_valid_i(ack_valid),
        .dcache_store_ack_lsq_tag_i(ack_tag),
        .dcache_store_ack_error_i('0),
        .store_ack_query_valid_i('0),
        .store_ack_query_tag_i('0),
        .store_ack_ready_i(1'b1),
        .report_recovery_packet_i('0),
        .occupancy_o(occupancy),.load_complete_valid_o(load_valid),.load_complete_value_o(load_value),.load_complete_error_o(load_error),.load_complete_rob_tag_o(load_rob_tag),.load_complete_phys_rd_o(selected_phys),.alloc_ready_o(alloc_ready),.alloc_lsq_tag_o(alloc_tag),.store_commit_ready_o(commit_ready),
        .dcache_req_mmio_class_o(saved_mmio_class),.dcache_req_mmio_valid_o(admitted_mmio),.dcache_req_valid_o(request_valid),.dcache_req_is_store_o(request_store),
        .dcache_req_addr_o(request_addr),.dcache_req_wdata_o(request_data),.dcache_req_mask_o(request_mask),
        .dcache_req_lsq_tag_o(request_tag),.store_ack_valid_o(store_ack_valid)
    );
    always @(posedge clk) if(!reset && monitor_loads && request_valid && request_ready) begin
        if(request_store || request_tag!==ticket || request_addr!==expected_addr)
            $fatal(1,"allocation load request identity/payload changed");
        requests=requests+1;
    end
    task tick;begin @(posedge clk);#1;end endtask
    task clear;begin
        @(negedge clk);reset=1;alloc_valid=0;loads=0;stores=0;request_ready=0;response_valid=0;recovery=0;commit_valid=0;ack_valid=0;monitor_loads=1;load_ready=0;updates=0;allocation_data_ready=1;
        tick;tick;@(negedge clk);reset=0;requests=0;
    end endtask
    task offer(input [31:0] address,input [1:0] size,input unsigned_bit);
        begin
            alloc_valid=1;loads=1;stores=0;alloc_rob=32'h101;alloc_addr=address;alloc_size=size;
            unsigned_load=unsigned_bit;expected_addr=address;#1;ticket=alloc_tag[15:0];
            if(!alloc_ready || !request_valid || request_store || request_tag!=ticket || request_addr!=address)
                $fatal(1,"fresh owned load did not offer on allocation edge");
        end
    endtask
    task response(input [31:0] data,input [31:0] expected);
        begin
            response_valid=1;response_tag=ticket;response_data=data;tick;@(negedge clk);response_valid=0;#1;
            if(!load_valid || load_error || load_rob_tag!=16'h101 || selected_phys!=9 || load_value!=expected)
                $fatal(1,"allocation request response lost exact row/data/phys identity");
        end
    endtask
    initial begin
        // Accepted on allocation edge: saved row starts sent/waiting, and no
        // selection ticket survives to repeat the cache access.
        clear;offer(32'h100,2,0);request_ready=1;tick;@(negedge clk);alloc_valid=0;loads=0;#1;
        if(request_valid || requests!=1 || occupancy!=1) $fatal(1,"accepted allocation load reoffered");
        request_ready=0;response(32'h11223344,32'h11223344);
        // First offer stalled: original ticket owns the same packet after
        // inputs change, then it sends once and accepts a byte response.
        clear;offer(32'h101,0,1);tick;@(negedge clk);alloc_valid=0;loads=0;alloc_addr=32'hdeadbeef;#1;
        if(!request_valid || request_tag!=ticket || request_addr!=32'h101 || request_mask!=16'h0002)
            $fatal(1,"backpressured allocation load was not retained");
        tick;@(negedge clk);request_ready=1;tick;@(negedge clk);request_ready=0;#1;
        if(request_valid || requests!=1) $fatal(1,"held allocation load duplicated");
        response(32'h80,32'h80);
        // Existing request queries still forward bytes from an older owned
        // store, including a partial mask that must fetch uncovered bytes.
        clear;alloc_valid=1;stores=1;alloc_addr=32'h101;alloc_data=32'h7f;alloc_size=0;alloc_rob=32'h109;
        tick;@(negedge clk);stores=0;loads=1;alloc_addr=32'h100;alloc_size=2;alloc_rob=32'h101;#1;
        ticket=alloc_tag[15:0];expected_addr=32'h100;tick;@(negedge clk);alloc_valid=0;loads=0;
        for(limit=0;limit<8 && !request_valid;limit=limit+1) begin tick;@(negedge clk);end
        if(!request_valid || request_store || request_tag!=ticket || request_mask!=16'h000d || mmio_class)
            $fatal(1,"saved query changed ordinary partial forwarding request");
        request_ready=1;tick;@(negedge clk);request_ready=0;response(32'h11223344,32'h11227f44);
        // An existing fully covered word must complete without sending a
        // cache request; saved-query validity preserves full-forward suppression.
        clear;alloc_valid=1;stores=1;alloc_addr=32'h100;alloc_data=32'h55667788;alloc_size=2;alloc_rob=32'h109;
        tick;@(negedge clk);stores=0;loads=1;alloc_addr=32'h100;alloc_size=2;alloc_rob=32'h101;
        tick;@(negedge clk);alloc_valid=0;loads=0;
        for(limit=0;limit<8 && !load_valid;limit=limit+1) begin
            #1;if(request_valid) $fatal(1,"fully forwarded load queried cache");
            tick;@(negedge clk);
        end
        if(!load_valid || load_value!=32'h55667788 || load_error)
            $fatal(1,"saved query lost fully forwarded result");
        // Irrelevant data updates for a completed load cannot overwrite its
        // held result in a shared word. The old implementation updates only
        // its unused store-operand bank in this situation.
        updates=1;update_tag=ticket;update_data=32'hdeadbeef;
        tick;@(negedge clk);updates=0;#1;
        if(!load_valid || load_value!=32'h55667788) $fatal(1,"load result overwritten by store-data event");
        // Delayed store data owns the shared word, then supplies a fully
        // forwarded younger load through the original exact-tag update.
        clear;alloc_valid=1;stores=1;allocation_data_ready=0;alloc_addr=32'h100;
        alloc_data=0;alloc_size=2;alloc_rob=32'h109;#1;update_tag=alloc_tag[15:0];
        tick;@(negedge clk);stores=0;loads=1;allocation_data_ready=1;alloc_rob=32'h101;
        #1;ticket=alloc_tag[15:0];tick;@(negedge clk);alloc_valid=0;loads=0;#1;
        if(request_valid || load_valid) $fatal(1,"load crossed unresolved store operand");
        updates=1;update_data=32'haabbccdd;tick;@(negedge clk);updates=0;
        for(limit=0;limit<8 && !load_valid;limit=limit+1) begin
            #1;if(request_valid) $fatal(1,"fully forwarded delayed store queried cache");
            tick;@(negedge clk);
        end
        if(!load_valid || load_value!=32'haabbccdd) $fatal(1,"delayed store operand lost");
        // Fill four rows with accepted loads. On the full head's report/pop
        // edge, an actual allocation replaces that same row with a store.
        clear;monitor_loads=0;request_ready=1;
        for(row=0;row<4;row=row+1) begin
            alloc_valid=1;loads=1;stores=0;alloc_rob=32'h101+row*8;
            alloc_addr=32'h100+row*4;alloc_size=2;#1;tickets[row]=alloc_tag[15:0];
            if(!alloc_ready || !request_valid) $fatal(1,"row-reuse fixture could not fill load queue");
            tick;@(negedge clk);alloc_valid=0;loads=0;
        end
        request_ready=0;response_valid=1;response_tag=tickets[0];response_data=32'h11223344;
        tick;@(negedge clk);response_valid=0;#1;
        if(occupancy!=4 || !load_valid || load_value!=32'h11223344) $fatal(1,"full head result was not held");
        load_ready=1;alloc_valid=1;stores=1;alloc_rob=32'h129;alloc_addr=32'h200;
        alloc_data=32'hcafebabe;alloc_size=2;#1;reused_ticket=alloc_tag[15:0];
        if(!alloc_ready || reused_ticket==tickets[0]) $fatal(1,"same-edge pop did not allocate new full generation");
        tick;@(negedge clk);load_ready=0;alloc_valid=0;stores=0;
        response_valid=1;response_tag=tickets[0];response_data=32'hdeadbeef;
        tick;@(negedge clk);response_valid=0;commit_valid=1;commit_tag=16'h129;#1;
        for(limit=0;limit<8 && !request_valid;limit=limit+1) begin tick;@(negedge clk);end
        if(occupancy!=4 || !request_valid || !request_store || request_tag!=reused_ticket ||
           request_addr!=32'h200 || request_data[31:0]!=32'hcafebabe || request_mask!=16'h000f)
            $fatal(1,"old load result/stale response overwrote reallocated store");
        // Held exact MMIO classification remains true through backpressure.
        // After ACK/pop, its invalid payload may remain in the selection owner;
        // that stale payload must not classify the next fresh load as MMIO.
        clear;monitor_loads=0;alloc_valid=1;stores=1;alloc_addr=32'h80000000;alloc_data=32'h12345678;
        alloc_size=2;alloc_rob=32'h109;tick;@(negedge clk);alloc_valid=0;stores=0;
        commit_valid=1;commit_tag=16'h109;#1;
        if(!commit_ready || !request_valid || !request_store || !mmio_class)
            $fatal(1,"exact MMIO admission classification missing");
        exit_ticket=request_tag;tick;@(negedge clk);commit_valid=0;#1;
        if(!request_valid || !mmio_class || request_tag!=exit_ticket) $fatal(1,"held MMIO classification changed");
        request_ready=1;tick;@(negedge clk);request_ready=0;ack_valid=1;ack_tag=exit_ticket;
        tick;@(negedge clk);ack_valid=0;
        for(limit=0;limit<6 && occupancy!=0;limit=limit+1) begin tick;@(negedge clk);end
        if(occupancy!=0 || request_valid || mmio_class) $fatal(1,"invalid stale MMIO owner leaked classification");
        monitor_loads=1;offer(32'h100,2,0);#1;if(mmio_class) $fatal(1,"fresh load classified by stale exit payload");
        request_ready=1;tick;@(negedge clk);alloc_valid=0;loads=0;request_ready=0;
        response(32'h11223344,32'h11223344);
        // Any old store blocks the fresh shortcut, even with a known nonalias
        // address; current recovery also blocks it.
        clear;alloc_valid=1;stores=1;alloc_addr=32'h200;alloc_size=2;alloc_rob=32'h109;
        tick;@(negedge clk);stores=0;loads=1;alloc_addr=32'h100;alloc_rob=32'h101;#1;
        if(request_valid) $fatal(1,"allocation request crossed old store");
        clear;recovery=1;alloc_valid=1;loads=1;#1;
        if(request_valid) $fatal(1,"allocation request crossed recovery");
        done=1;
    end
    initial begin #3000;$fatal(1,"allocation request sample timeout");end
endmodule

module rv32_lsq_mmio_admission_tb;
    wire old_done,new_done;
    rv32_lsq_mmio_admission_fixture #(.EARLY(0)) old_impl (.done(old_done));
    rv32_lsq_mmio_admission_fixture #(.EARLY(1)) new_impl (.done(new_done));
    // Compare observable public handshakes and their owned payloads. Unowned
    // stale words are not required to agree across the two storage policies.
    always @(negedge old_impl.clk) begin
        #3;
        if(!old_impl.reset && !new_impl.reset) begin
            if({old_impl.alloc_ready,old_impl.commit_ready,old_impl.request_valid,old_impl.store_ack_valid,old_impl.load_valid,old_impl.occupancy} !==
               {new_impl.alloc_ready,new_impl.commit_ready,new_impl.request_valid,new_impl.store_ack_valid,new_impl.load_valid,new_impl.occupancy})
                $fatal(1,"saved-query LSQ public handshake/cycle mismatch");
            if(old_impl.routed_mmio !== new_impl.routed_mmio ||
               new_impl.routed_mmio !== new_impl.original_mmio_class)
                $fatal(1,"saved MMIO routing differs from original qualified predicate");
            if(old_impl.request_valid &&
               {old_impl.request_store,old_impl.request_addr,old_impl.request_tag,old_impl.request_mask,old_impl.request_data} !==
               {new_impl.request_store,new_impl.request_addr,new_impl.request_tag,new_impl.request_mask,new_impl.request_data})
                $fatal(1,"saved-query LSQ owned request payload mismatch");
            if(old_impl.load_valid &&
               {old_impl.load_value,old_impl.load_rob_tag,old_impl.selected_phys,old_impl.load_error} !==
               {new_impl.load_value,new_impl.load_rob_tag,new_impl.selected_phys,new_impl.load_error})
                $fatal(1,"saved-query LSQ owned completion payload mismatch");
        end
    end
    initial begin
        wait(old_done && new_done);#4;
        $display("PASS: limited paired LSQ MMIO-admission sample");$finish;
    end
endmodule
