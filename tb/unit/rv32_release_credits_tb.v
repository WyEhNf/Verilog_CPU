`timescale 1ns/1ps

module release_rob_sample #(
    parameter UNUSED=0,
    parameter integer BE_WIDTH = 2,
    parameter integer ROB_ENTRIES = 4,
    parameter integer ASAP7_FANOUT_BUFFERS = 0,
    parameter integer ROB_CONTROL_REGISTER_BANKS = 0,
    parameter integer COMMIT_BANKED_READ = 0,
    parameter integer ALLOC_BANKED_WRITE = 1
)(output reg done=0);
    localparam integer PHYS_AW = 6;
    localparam integer SLOT_W = $clog2(ROB_ENTRIES);
    localparam integer GEN_W = 8;
    localparam integer TAG_W = 1 + 2 + SLOT_W + GEN_W;
    localparam integer CP_W = 32;
    localparam integer COUNT_W = $clog2(ROB_ENTRIES + 1);
    localparam integer ACW = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);
    reg clk, reset;
    reg [BE_WIDTH-1:0] alloc_valid, alloc_rd_we, alloc_store, alloc_branch, alloc_halt, alloc_error;
    reg [(BE_WIDTH*32)-1:0] alloc_pc, alloc_inst;
    reg [(BE_WIDTH*5)-1:0] alloc_rd;
    reg [(BE_WIDTH*PHYS_AW)-1:0] alloc_old, alloc_new;
    reg [(BE_WIDTH*CP_W)-1:0] alloc_cp;
    wire alloc_ready;
    wire [BE_WIDTH-1:0] alloc_fire;
    wire [(BE_WIDTH*TAG_W)-1:0] alloc_tag;
    wire [ACW-1:0] alloc_count;
    reg [BE_WIDTH-1:0] cpl_valid, cpl_done, cpl_error;
    reg [(BE_WIDTH*TAG_W)-1:0] cpl_tag;
    reg [(BE_WIDTH*32)-1:0] cpl_value, cpl_addr;
    reg [(BE_WIDTH*4)-1:0] cpl_mask;
    reg [(BE_WIDTH*32)-1:0] cpl_data;
    reg commit_ready;
    wire [BE_WIDTH-1:0] commit_valid, commit_rd_we, commit_store;
    wire [(BE_WIDTH*5)-1:0] commit_rd;
    wire [(BE_WIDTH*32)-1:0] commit_pc, commit_inst, commit_value, commit_addr;
    wire [(BE_WIDTH*16)-1:0] commit_mask;
    wire [(BE_WIDTH*128)-1:0] commit_data;
    wire [(BE_WIDTH*TAG_W)-1:0] commit_tag;
    wire store_valid;
    reg store_ready, store_ack_valid, store_ack_error;
    wire [TAG_W-1:0] store_tag;
    wire [31:0] store_addr;
    wire [15:0] store_mask;
    wire [127:0] store_data;
    reg [BE_WIDTH-1:0] recovery_valid;
    reg [(BE_WIDTH*TAG_W)-1:0] recovery_tag;
    reg [(BE_WIDTH*32)-1:0] recovery_pc;
    wire recovery_accept, redirect_valid, checkpoint_valid;
    wire [31:0] redirect_pc;
    wire [3:0] redirect_epoch;
    wire [CP_W-1:0] checkpoint;
    wire recovery_rd_we;
    wire [4:0] recovery_rd;
    wire [PHYS_AW-1:0] recovery_new_phys;
    wire [(1<<PHYS_AW)-1:0] recovery_reclaim_bitmap;
    wire [PHYS_AW:0] recovery_reclaim_count;
    wire [(BE_WIDTH*PHYS_AW)-1:0] commit_old_phys, commit_new_phys;
    reg [TAG_W-1:0] store_ack_tag;
    wire halted, error;
    wire [31:0] return_value;
    wire [SLOT_W-1:0] head, tail;
    wire [COUNT_W-1:0] occupancy;
    integer bad;
    integer j;
    reg [TAG_W-1:0] saved_tag0, saved_tag1, saved_store_tag, saved_branch_tag, stale_tag;
    reg [TAG_W-1:0] reused_tag, current_tag;
    integer rotation, rotation_lane, rotation_checks;
    reg [ROB_ENTRIES-1:0] visited_heads;
    reg [(BE_WIDTH*TAG_W)-1:0] rotation_tags;
    reg [(BE_WIDTH*32)-1:0] held_pc, held_inst, held_value;
    reg [SLOT_W-1:0] held_head;

    wire [ACW-1:0] release_count;
    rv32_rob #(.RELEASE_CREDITS(1), .BE_WIDTH(BE_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .PHYS_REGS(1<<PHYS_AW), .PHYS_ADDR_WIDTH(PHYS_AW), .CHECKPOINT_WIDTH(CP_W), .STORE_BUFFERED_RETIRE(0), .ASAP7_FANOUT_BUFFERS(ASAP7_FANOUT_BUFFERS), .ROB_CONTROL_REGISTER_BANKS(ROB_CONTROL_REGISTER_BANKS), .COMMIT_BANKED_READ(COMMIT_BANKED_READ), .ALLOC_BANKED_WRITE(ALLOC_BANKED_WRITE)) dut (
        .clk_i(clk), .reset_i(reset), .alloc_valid_i(alloc_valid), .alloc_pc_i(alloc_pc), .alloc_inst_i(alloc_inst), .alloc_rd_i(alloc_rd), .alloc_rd_we_i(alloc_rd_we),
        .alloc_old_phys_i(alloc_old), .alloc_new_phys_i(alloc_new), .alloc_is_store_i(alloc_store), .alloc_is_branch_i(alloc_branch), .alloc_is_halt_i(alloc_halt), .alloc_is_error_i(alloc_error), .alloc_checkpoint_i(alloc_cp),
        .alloc_ready_o(alloc_ready), .alloc_fire_o(alloc_fire), .alloc_tag_o(alloc_tag), .alloc_count_o(alloc_count),.allocation_release_count_o(release_count),
        .completion_valid_i(cpl_valid), .completion_tag_i(cpl_tag), .completion_value_i(cpl_value), .completion_done_i(cpl_done), .completion_error_i(cpl_error), .completion_store_addr_i(cpl_addr), .completion_store_mask_i(cpl_mask), .completion_store_data_i(cpl_data),
        .commit_ready_i(commit_ready), .commit_valid_o(commit_valid), .commit_rd_we_o(commit_rd_we), .commit_rd_o(commit_rd), .commit_pc_o(commit_pc), .commit_inst_o(commit_inst), .commit_value_o(commit_value), .commit_is_store_o(commit_store), .commit_store_addr_o(commit_addr), .commit_store_mask_o(commit_mask), .commit_store_data_o(commit_data), .commit_tag_o(commit_tag), .commit_old_phys_o(commit_old_phys), .commit_new_phys_o(commit_new_phys),
        .store_commit_valid_o(store_valid), .store_commit_ready_i(store_ready), .store_commit_tag_o(store_tag), .store_commit_addr_o(store_addr), .store_commit_mask_o(store_mask), .store_commit_data_o(store_data), .store_ack_valid_i(store_ack_valid), .store_ack_tag_i(store_ack_tag), .store_ack_error_i(store_ack_error),
        .recovery_apply_i(1'b0),.recovery_hold_i(1'b0),.fast_store_valid_i('0),.fast_store_tag_i('0),.recovery_valid_i(recovery_valid), .recovery_tag_i(recovery_tag), .recovery_pc_i(recovery_pc), .recovery_accept_o(recovery_accept), .redirect_valid_o(redirect_valid), .redirect_pc_o(redirect_pc), .redirect_epoch_o(redirect_epoch), .checkpoint_restore_valid_o(checkpoint_valid), .checkpoint_restore_o(checkpoint), .recovery_rd_we_o(recovery_rd_we), .recovery_rd_o(recovery_rd), .recovery_new_phys_o(recovery_new_phys), .recovery_reclaim_bitmap_o(recovery_reclaim_bitmap), .recovery_reclaim_count_o(recovery_reclaim_count),
        .halted_o(halted), .error_o(error), .return_value_o(return_value), .head_o(head), .tail_o(tail), .occupancy_o(occupancy)
    );
    initial begin clk=0;forever #5 clk=~clk;end
    task tick;begin @(posedge clk);#1;end endtask
    initial begin
        reset=1;alloc_valid=0;alloc_rd_we=0;alloc_store=0;alloc_branch=0;alloc_halt=0;alloc_error=0;
        alloc_pc=0;alloc_inst=0;alloc_rd=0;alloc_old=0;alloc_new=0;alloc_cp=0;
        cpl_valid=0;cpl_done=0;cpl_error=0;cpl_tag=0;cpl_value=0;cpl_addr=0;cpl_mask=0;cpl_data=0;
        commit_ready=0;store_ready=0;store_ack_valid=0;store_ack_error=0;store_ack_tag=0;
        recovery_valid=0;recovery_tag=0;recovery_pc=0;
        tick;@(negedge clk);reset=0;alloc_valid=3;#1;rotation_tags=alloc_tag;
        tick;@(negedge clk);#1;held_pc=alloc_tag;tick;@(negedge clk);alloc_valid=0;
        cpl_valid=3;cpl_done=3;cpl_tag=rotation_tags;tick;@(negedge clk);cpl_valid=0;alloc_valid=3;#1;
        if(occupancy!=4 || alloc_fire!=0 || release_count!=0) $fatal(1,"ROB borrowed while commit stalled");
        commit_ready=1;#1;stale_tag=rotation_tags[0+:TAG_W];reused_tag=alloc_tag[0+:TAG_W];
        if(alloc_fire!=3 || release_count!=2 || reused_tag==stale_tag || commit_tag!=rotation_tags)
            $fatal(1,"ROB full-prefix replacement identity failed");
        tick;@(negedge clk);alloc_valid=0;commit_ready=0;
        cpl_valid=3;cpl_tag=held_pc[0+:2*TAG_W];tick;@(negedge clk);cpl_valid=0;commit_ready=1;
        tick;@(negedge clk);commit_ready=0;cpl_valid=1;cpl_tag=stale_tag;
        tick;@(negedge clk);cpl_valid=0;#1;
        if(occupancy!=2 || commit_valid!=0) $fatal(1,"ROB stale completion readied recycled owner");
        cpl_valid=1;cpl_tag=reused_tag;tick;@(negedge clk);cpl_valid=0;#1;
        if(!commit_valid[0] || commit_tag[0+:TAG_W]!=reused_tag) $fatal(1,"ROB new completion lost");
        done=1;
    end
endmodule

`timescale 1ns/1ps
module release_lsq_sample(output reg done=0);
    reg clk=0,reset=1,recovery=0;
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
    integer requests=0;
    reg [15:0] ticket;
    reg [31:0] expected_addr;
    reg [127:0] expected_data;
    reg [15:0] expected_mask;
    reg ack_ready=0;wire release_credit;wire [2:0] occupancy;wire [1:0] alloc_fire;
    rv32_lsq #(.RELEASE_CREDITS(1), .BE_WIDTH(2),.LSQ_ENTRIES(4),.ROB_ENTRIES(8),.TAG_WIDTH(16),.ROB_TAG_WIDTH(16),
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
        .alloc_is_load_i('0),
        .alloc_is_store_i(alloc_valid),
        .alloc_rob_tag_i(alloc_rob),
        .alloc_phys_rd_i('0),
        .alloc_size_i(alloc_size),
        .alloc_unsigned_i('0),
        .alloc_addr_valid_i(alloc_valid),
        .alloc_addr_i(alloc_addr),
        .alloc_data_valid_i(alloc_valid),
        .alloc_store_data_i(alloc_data),
        .alloc_store_mask_i('0),
        .early_addr_valid_i('0),
        .early_addr_tag_i('0),
        .early_addr_i('0),
        .addr_update_valid_i('0),
        .addr_update_tag_i('0),
        .addr_update_i('0),
        .data_update_valid_i('0),
        .data_update_tag_i('0),
        .data_update_i('0),
        .data_mask_update_i('0),
        .wakeup_valid_i('0),
        .wakeup_tag_i('0),
        .wakeup_value_i('0),
        .store_commit_valid_i(commit_valid),
        .store_commit_rob_tag_i(commit_tag),
        .dcache_req_ready_i(request_ready),
        .dcache_resp_valid_i('0),
        .dcache_resp_lsq_tag_i('0),
        .dcache_resp_query_valid_i('0),
        .dcache_resp_query_tags_i('0),
        .dcache_resp_addr_i('0),
        .dcache_resp_line_data_i('0),
        .dcache_resp_word_data_i('0),
        .dcache_resp_line_valid_i('0),
        .dcache_resp_error_i('0),
        .load_complete_ready_i(1'b1),
        .dcache_store_ack_valid_i(ack_valid),
        .dcache_store_ack_lsq_tag_i(ack_tag),
        .dcache_store_ack_error_i('0),
        .store_ack_query_valid_i('0),
        .store_ack_query_tag_i('0),
        .store_ack_ready_i(ack_ready),
        .report_recovery_packet_i('0),
        .allocation_release_o(release_credit),.occupancy_o(occupancy),.alloc_fire_o(alloc_fire),.alloc_ready_o(alloc_ready),.alloc_lsq_tag_o(alloc_tag),.store_commit_ready_o(commit_ready),
        .dcache_req_valid_o(request_valid),.dcache_req_is_store_o(request_store),
        .dcache_req_addr_o(request_addr),.dcache_req_wdata_o(request_data),.dcache_req_mask_o(request_mask),
        .dcache_req_lsq_tag_o(request_tag),.store_ack_valid_o(store_ack_valid)
    );
    task tick;begin @(posedge clk);#1;end endtask
    reg [15:0] reused_tag;
    initial begin
        tick;@(negedge clk);reset=0;alloc_valid=3;alloc_size=4'ha;
        alloc_rob={16'h109,16'h101};alloc_addr={32'h104,32'h100};alloc_data=64'h2222222211111111;
        #1;ticket=alloc_tag[15:0];tick;@(negedge clk);
        alloc_rob={16'h119,16'h111};alloc_addr={32'h10c,32'h108};tick;@(negedge clk);alloc_valid=0;
        commit_valid=1;commit_tag=16'h101;#1;
        if(!commit_ready || !request_valid || request_tag!=ticket) $fatal(1,"LSQ store admission identity failed");
        request_ready=1;tick;@(negedge clk);commit_valid=0;request_ready=0;
        ack_valid=1;ack_tag=ticket;tick;@(negedge clk);ack_valid=0;alloc_valid=1;
        alloc_rob={16'b0,16'h121};alloc_addr=64'h110;alloc_data=64'h33333333;#1;
        if(occupancy!=4 || release_credit || alloc_fire) $fatal(1,"LSQ borrowed stalled ACK");
        ack_ready=1;#1;reused_tag=alloc_tag[15:0];
        if(!release_credit || alloc_fire!=1 || reused_tag==ticket || !store_ack_valid)
            $fatal(1,"LSQ full-head replacement failed");
        tick;@(negedge clk);alloc_valid=0;ack_ready=0;ack_valid=1;ack_tag=ticket;
        tick;@(negedge clk);ack_valid=0;#1;
        if(occupancy!=4) $fatal(1,"LSQ capacity count changed on stale ACK");
        // Inspect the recycled row after a stale ACK. It has not sent a new
        // request, and must retain clean ACK/completion metadata.
        if(dut.store_ack_mem[0] || dut.request_sent_mem[0] || dut.complete_mem[0])
            $fatal(1,"LSQ old ACK leaked into recycled row");
        done=1;
    end
endmodule

`timescale 1ns/1ps
module release_rs_sample(output reg done=0);
    reg clk=0,reset=1,flush=0;
    always #5 clk=~clk;
    reg [1:0] alloc=0,issue_ready=0;
    reg [63:0] pc=0;
    reg [31:0] tag=0;
    wire [1:0] fire,issue_valid,release_count;
    wire [63:0] issue_pc;
    wire [31:0] issue_tag;
    wire [2:0] occupancy;
    rv32_reservation_station #(.BE_WIDTH(2),.ENTRIES(4),.TAG_WIDTH(16),.SOURCE_TAG_WIDTH(16),
        .AGE_WIDTH(8),.AGE_ORDER_MATRIX(2),.ALLOC_STATIC_WRITE(1),.LOCAL_PAYLOAD_ROWS(1),.RELEASE_CREDITS(1)) dut (
        .clk_i(clk),
        .reset_i(reset),
        .alloc_valid_i(alloc),
        .alloc_op_i('0),
        .alloc_pc_i(pc),
        .alloc_rob_tag_i(tag),
        .alloc_target_live_i(alloc),
        .alloc_phys_rd_i('0),
        .alloc_src1_value_i('0),
        .alloc_src1_tag_i('0),
        .alloc_src1_ready_i(2'b11),
        .alloc_src2_value_i('0),
        .alloc_src2_tag_i('0),
        .alloc_src2_ready_i(2'b11),
        .alloc_store_data_i('0),
        .alloc_metadata_i('0),
        .allocation_release_count_o(release_count),
        .alloc_fire_o(fire),
        .wake_valid_i('0),
        .wake_tag_i('0),
        .wake_value_i('0),
        .issue_ready_i(issue_ready),
        .entry_recovery_qualified_i('0),
        .entry_issue_cancel_i('0),
        .issue_valid_o(issue_valid),
        .issue_pc_o(issue_pc),
        .issue_rob_tag_o(issue_tag),
        .flush_valid_i(flush),
        .flush_kill_mask_i('0),
        .occupancy_o(occupancy)
    );
    task tick;begin @(posedge clk);#1;end endtask
    initial begin
        tick;@(negedge clk);reset=0;alloc=3;pc={32'd20,32'd10};tag={16'h109,16'h101};
        tick;@(negedge clk);pc={32'd40,32'd30};tag={16'h119,16'h111};tick;@(negedge clk);
        pc={32'd60,32'd50};tag={16'h129,16'h121};#1;
        if(occupancy!=4 || fire!=0 || release_count!=0) $fatal(1,"RS borrowed stalled issue");
        issue_ready=3;#1;
        if(fire!=3 || release_count!=2 || issue_pc!={32'd20,32'd10}) $fatal(1,"RS full replacement old payload failed");
        tick;@(negedge clk);alloc=0;#1;
        if(occupancy!=4 || issue_pc!={32'd40,32'd30}) $fatal(1,"RS replacement violated retained age order");
        tick;@(negedge clk);issue_ready=0;#1;
        if(occupancy!=2 || issue_valid!=3 || issue_pc!={32'd60,32'd50} || issue_tag!={16'h129,16'h121})
            $fatal(1,"RS issue clear destroyed new payload/live owner");
        flush=1;#1;if(release_count!=0) $fatal(1,"RS borrowed recovery release");
        done=1;
    end
endmodule
module rv32_release_credits_tb;
    wire a,b,c;
    release_rob_sample rob_sample(a);
    release_lsq_sample lsq_sample(b);
    release_rs_sample rs_sample(c);
    initial begin wait(a&&b&&c);$display("PASS: limited shared release-credit sample");$finish;end
    initial begin #2000;$fatal(1,"release sample timeout");end
endmodule
