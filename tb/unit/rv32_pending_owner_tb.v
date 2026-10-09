`timescale 1ns/1ps
`include "rv32im_defs.vh"
module rv32_pending_owner_fixture #(parameter integer DIRECT=0)(output reg done=0);
    localparam integer BW=2,TW=16;
    reg clk=0,reset=1,flush=0;always #5 clk=~clk;
    reg [1:0] trace_valid=0;
    reg [63:0] pc=0,imm=0;
    reg [11:0] op=0;
    reg [9:0] rd=0;
    reg [1:0] rdwe=0,isload=0,isbranch=0;
    wire [1:0] ready[0:1],commit_valid[0:1],commit_rdwe[0:1];
    wire [63:0] commit_pc[0:1],commit_value[0:1];
    wire [31:0] commit_tag[0:1];
    wire [1:0] req_valid,req_load,resp_ready,redirect,halted,error;
    wire [31:0] req_addr[0:1],redirect_pc[0:1];
    wire [15:0] req_tag[0:1];
    reg commit_ready=0,resp_valid=0;
    reg [15:0] held_load_tag=0;
    reg held_load_seen=0;
    integer read_count=0,received=0,expected=0,timeout_count,i,lane;
    integer captures=0,previews=0,applies=0,pending_edges=0;
    reg [15:0] first_branch_tag=0;
    reg [31:0] expected_pc[0:31],expected_value[0:31];
    reg expected_we[0:31];
    genvar policy;
    generate for(policy=0;policy<2;policy=policy+1) begin:g_backend
        rv32_backend_joint #(.BE_WIDTH(BW),.ROB_ENTRIES(8),.PHYS_REGS(40),
            .RS_ENTRIES(4),.LSQ_ENTRIES(4),.TAG_WIDTH(TW),.CDB_WIDTH(2),.INT_ISSUE_WIDTH(2),
            .PRF_VALUE_SRAM(1),.PRF_READ_MUX_IMPL(1),.CHECKPOINT_IMPL(1),.RAT_RECOVERY_IMPL(1),
            .LOCAL_EXEC_RECOVERY(1),.RECOVERY_DIRECT_APPLY(DIRECT),.RECOVERY_ROB_CREDIT(1),
            .ROB_RECOVERY_PENDING_OWNER(policy),.ROB_COMPLETION_COMMIT_BYPASS(1)) dut (
            .clk_i(clk),.reset_i(reset),.flush_i(flush),
            .trace_valid_i(trace_valid),.trace_ready_o(ready[policy]),.trace_pc_i(pc),
            .trace_inst_i(64'b0),.trace_op_i(op),.trace_imm_i(imm),.trace_rd_i(rd),
            .trace_rs1_i(10'b0),.trace_rs2_i(10'b0),.trace_rd_we_i(rdwe),
            .trace_rs1_used_i(isbranch),.trace_rs2_used_i(isbranch),
            .trace_is_load_i(isload),.trace_is_store_i(2'b0),.trace_is_branch_i(isbranch),
            .trace_is_halt_i(2'b0),.trace_is_error_i(2'b0),.trace_mem_size_i(4'b1010),
            .trace_mem_unsigned_i(2'b0),.trace_store_data_i(256'b0),
            .trace_pred_taken_i(2'b0),.trace_pred_target_i(64'b0),
            .trace_pred_kind_i(4'b0101),.trace_pred_metadata_i(32'b0),
            .dcache_req_valid_o(req_valid[policy]),.dcache_req_ready_i(1'b1),
            .dcache_req_is_load_o(req_load[policy]),.dcache_req_addr_o(req_addr[policy]),
            .dcache_req_lsq_tag_o(req_tag[policy]),
            .dcache_resp_valid_i(resp_valid),.dcache_resp_ready_o(resp_ready[policy]),
            .dcache_resp_lsq_tag_i(held_load_tag),.dcache_resp_query_valid_i(2'b0),
            .dcache_resp_query_tags_i(32'b0),.dcache_resp_addr_i(32'h20),
            .dcache_resp_line_data_i(128'b0),.dcache_resp_word_data_i(32'h12345678),
            .dcache_resp_line_valid_i(1'b0),.dcache_resp_error_i(1'b0),
            .dcache_store_ack_valid_i(1'b0),.dcache_store_ack_lsq_tag_i(16'b0),
            .dcache_store_ack_error_i(1'b0),.store_ack_query_valid_i(2'b0),
            .store_ack_query_tag_i(32'b0),.commit_ready_i(commit_ready),
            .commit_valid_o(commit_valid[policy]),.commit_pc_o(commit_pc[policy]),
            .commit_rd_we_o(commit_rdwe[policy]),.commit_value_o(commit_value[policy]),
            .commit_tag_o(commit_tag[policy]),.redirect_valid_o(redirect[policy]),
            .redirect_pc_o(redirect_pc[policy]),.halted_o(halted[policy]),.error_o(error[policy]));
    end endgenerate
    always @(negedge clk) begin
        #2;
        if(!reset) begin
            assert({ready[0],commit_valid[0],req_valid[0],resp_ready[0],redirect[0],halted[0],error[0]}==
                   {ready[1],commit_valid[1],req_valid[1],resp_ready[1],redirect[1],halted[1],error[1]})
                else $fatal(1,"Pending owner changed a public handshake/cycle, direct=%0d",DIRECT);
            for(lane=0;lane<BW;lane=lane+1) if(commit_valid[0][lane])
                assert({commit_pc[0][lane*32+:32],commit_value[0][lane*32+:32],commit_rdwe[0][lane],commit_tag[0][lane*TW+:TW]}==
                       {commit_pc[1][lane*32+:32],commit_value[1][lane*32+:32],commit_rdwe[1][lane],commit_tag[1][lane*TW+:TW]})
                    else $fatal(1,"Pending owner changed valid commit packet");
            if(req_valid[0]) assert({req_load[0],req_addr[0],req_tag[0]}=={req_load[1],req_addr[1],req_tag[1]});
            if(redirect[0]) assert(redirect_pc[0]==redirect_pc[1]);
            assert({g_backend[0].dut.branch_pending,g_backend[0].dut.rob_head,
                    g_backend[0].dut.rob_tail,g_backend[0].dut.rob_occupancy,g_backend[0].dut.rob_entry_valid,
                    g_backend[0].dut.rob_entry_generation,g_backend[0].dut.free_bitmap_state}==
                   {g_backend[1].dut.branch_pending,g_backend[1].dut.rob_head,
                    g_backend[1].dut.rob_tail,g_backend[1].dut.rob_occupancy,g_backend[1].dut.rob_entry_valid,
                    g_backend[1].dut.rob_entry_generation,g_backend[1].dut.free_bitmap_state})
                else $fatal(1,"Pending owner changed row ownership/allocator state");
        end
    end
    always @(posedge clk) if(!reset) begin
        if(req_valid[0]) begin
            assert(req_load[0] && req_addr[0]==32'h20) else $fatal(1,"Unexpected load request");
            held_load_tag<=req_tag[0];held_load_seen<=1;read_count=read_count+1;
        end
        if(g_backend[1].dut.branch_capture_write) begin
            captures=captures+1;
            if(captures==1) first_branch_tag=g_backend[1].dut.branch_capture_next[
                g_backend[1].dut.BRANCH_CAPTURE_WIDTH-1 -: TW];
        end
        if(g_backend[1].dut.rob_recovery_preview) previews=previews+1;
        if(g_backend[1].dut.rob_recovery_accept_source) applies=applies+1;
        if(g_backend[1].dut.branch_pending) pending_edges=pending_edges+1;
        if(commit_ready) for(integer c=0;c<BW;c=c+1) if(commit_valid[0][c]) begin
            if(received>=expected || commit_pc[0][c*32+:32]!==expected_pc[received] ||
                    commit_rdwe[0][c]!==expected_we[received] ||
                    (expected_we[received] && commit_value[0][c*32+:32]!==expected_value[received]))
                $fatal(1,"Unexpected committed packet direct=%0d index=%0d pc=%h value=%h",DIRECT,
                    received,commit_pc[0][c*32+:32],commit_value[0][c*32+:32]);
            received=received+1;
        end
    end
    task tick;begin @(posedge clk);#1;end endtask
    task expect_packet(input [31:0] p,input [31:0] v,input bit we);
        begin expected_pc[expected]=p;expected_value[expected]=v;expected_we[expected]=we;expected=expected+1;end
    endtask
    task send(input [1:0] valid,input [63:0] p,input [11:0] o,input [63:0] displacement,
            input [9:0] dest,input [1:0] we,input [1:0] load,input [1:0] branch);
        begin
            @(negedge clk);trace_valid=valid;pc=p;op=o;imm=displacement;rd=dest;
            rdwe=we;isload=load;isbranch=branch;#1;
            for(timeout_count=0;timeout_count<60 && ((ready[0]&valid)!=valid);timeout_count=timeout_count+1) begin
                if((ready[0]&valid)!=0) $fatal(1,"Sample requires atomic admission of its tiny bundle");
                tick;@(negedge clk);#1;
            end
            if((ready[0]&valid)!=valid) $fatal(1,"Trace admission timeout");
            tick;@(negedge clk);trace_valid=0;
        end
    endtask
    task wait_commits;
        begin
            for(timeout_count=0;timeout_count<100 && received!=expected;timeout_count=timeout_count+1) tick;
            if(received!=expected) $fatal(1,"Commit sample did not drain");
            @(negedge clk);
        end
    endtask
    task wait_pending;
        begin
            for(timeout_count=0;timeout_count<40 && !g_backend[1].dut.branch_pending;timeout_count=timeout_count+1) tick;
            if(!g_backend[1].dut.branch_pending) $fatal(1,"Branch did not capture a pending owner");
        end
    endtask
    initial begin
        tick;tick;@(negedge clk);reset=0;
        expect_packet(32'h1000,32'h12345678,1);expect_packet(32'h1004,3,1);
        expect_packet(32'h1008,0,0);expect_packet(32'h1048,7,1);
        send(1,64'h1000,{6'b0,`RV32IM_OP_LW},64'h20,10'd1,1,1,0);
        send(1,64'h1004,{6'b0,`RV32IM_OP_ADDI},64'd3,10'd2,1,0,0);
        // Both instructions acquire ROB identities together; the younger ADDI
        // may execute but recovery must remove it before architectural commit.
        send(3,{32'h100c,32'h1008},{`RV32IM_OP_ADDI,`RV32IM_OP_BEQ},
            {32'hbad,32'h40},{5'd3,5'd0},2'b10,0,2'b01);
        wait_pending;
        // Presents actual new work across apply, including optional direct
        // recovery allocation credits; staged mode preserves its hold.
        send(1,64'h1048,{6'b0,`RV32IM_OP_ADDI},64'd7,10'd3,1,0,0);
        if(!held_load_seen || read_count!=1) $fatal(1,"Older delayed load was not retained exactly once");
        @(negedge clk);resp_valid=1;tick;@(negedge clk);resp_valid=0;commit_ready=1;
        wait_commits;
        if(captures!=1 || applies!=1 || previews==0 || pending_edges<(DIRECT?1:2))
            $fatal(1,"Recovery lifecycle was not exercised");
        // Wrap and reuse all eight ROB rows with the original complete tags.
        for(i=0;i<8;i=i+1) begin
            expect_packet(32'h1100+i*4,32'(10+i),1);
            send(1,64'(32'h1100+i*4),{6'b0,`RV32IM_OP_ADDI},64'(10+i),10'd4,1,0,0);
        end
        wait_commits;
        if(g_backend[1].dut.rob_entry_generation[first_branch_tag[5:3]*10+:10]==first_branch_tag[6+:10])
            $fatal(1,"Recovery row generation reuse was not exercised");
        // Whole flush while the certificate is held clears the private owner.
        @(negedge clk);reset=1;commit_ready=0;tick;@(negedge clk);reset=0;
        send(1,64'h1200,{6'b0,`RV32IM_OP_BEQ},64'h40,0,0,0,1);wait_pending;
        @(negedge clk);flush=1;tick;@(negedge clk);flush=0;tick;
        if(g_backend[1].dut.branch_pending || g_backend[1].dut.recovery_descriptor_valid)
            $fatal(1,"Whole flush retained a pending recovery owner");
        @(negedge clk);reset=1;tick;@(negedge clk);reset=0;
        send(1,64'h1300,{6'b0,`RV32IM_OP_BEQ},64'h40,0,0,0,1);wait_pending;
        @(negedge clk);reset=1;tick;@(negedge clk);reset=0;tick;
        if(g_backend[1].dut.branch_pending || g_backend[1].dut.recovery_descriptor_valid)
            $fatal(1,"Reset retained a pending recovery owner");
        done=1;
        $display("PASS: pending-owner shared backend direct=%0d captures=%0d previews=%0d applies=%0d",DIRECT,captures,previews,applies);
    end
endmodule
module rv32_pending_owner_tb;
    wire staged_done,direct_done;
    rv32_pending_owner_fixture #(.DIRECT(0)) staged (.done(staged_done));
    rv32_pending_owner_fixture #(.DIRECT(1)) direct (.done(direct_done));
    initial begin wait(staged_done && direct_done);#4;$display("PASS: limited paired pending recovery ownership sample");$finish;end
    initial begin #6000;$fatal(1,"Pending owner sample timeout");end
endmodule
