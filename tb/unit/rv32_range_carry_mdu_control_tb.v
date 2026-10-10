`timescale 1ns/1ps
`include "rv32im_defs.vh"
module rv32_range_carry_mdu_control_fixture #(parameter integer DIRECT=0,ISSUE_STAGE=0)(output reg done=0);
    localparam integer BW=2,TW=16;
    reg clk=0,reset=1,flush=0;always #5 clk=~clk;
    reg [1:0] trace_valid=0;
    reg [63:0] pc=0,imm=0;
    reg [11:0] op=0;
    reg [9:0] rd=0;
    reg [1:0] rdwe=0,isload=0,isbranch=0;
    reg [9:0] source1=0,source2=0;
    reg [1:0] used1=0,used2=0;
    wire [1:0] ready[0:1],commit_valid[0:1],commit_rdwe[0:1];
    wire [63:0] commit_pc[0:1],commit_value[0:1];
    wire [31:0] commit_tag[0:1];
    wire [1:0] req_valid,req_load,resp_ready,redirect,halted,error;
    wire [31:0] req_addr[0:1],redirect_pc[0:1];
    wire [15:0] req_tag[0:1];
    reg commit_ready=0,resp_valid=0,resp_error=0,ack_valid=0;
    reg [15:0] held_store_tag=0;
    reg [3:0] mem_size=4'b1010;
    wire [1:0] isstore={(op[6 +: 6]==`RV32IM_OP_SW || op[6 +: 6]==`RV32IM_OP_SH || op[6 +: 6]==`RV32IM_OP_SB),
                      (op[0 +: 6]==`RV32IM_OP_SW || op[0 +: 6]==`RV32IM_OP_SH || op[0 +: 6]==`RV32IM_OP_SB)};
    wire [15:0] req_mask[0:1];
    wire [127:0] req_data[0:1];
    integer stores_seen=0,state_samples=0,mdu_samples=0,load_branch_wakes=0;
    reg [15:0] held_load_tag=0;
    reg held_load_seen=0;
    integer read_count=0,received=0,expected=0,timeout_count,i,lane;
    integer count_delta_edges=0;
    reg [2:0] count_delta_seen=0;
    integer captures=0,previews=0,applies=0,pending_edges=0;
    integer window_checks=0,window_head_checks=0,window_older_checks=0;
    reg [15:0] first_branch_tag=0;
    reg [31:0] expected_pc[0:31],expected_value[0:31];
    reg expected_we[0:31];
    genvar policy;
    generate for(policy=0;policy<2;policy=policy+1) begin:g_backend
        rv32_backend_joint #(.BE_WIDTH(BW),.ROB_ENTRIES(8),.PHYS_REGS(40),
            .RS_ENTRIES(8),.LSQ_ENTRIES(4),.TAG_WIDTH(TW),.CDB_WIDTH(2),.INT_ISSUE_WIDTH(2),
            .MUL_IMPL(2),.RS_ISSUE_METADATA(1),.RS_ARITHMETIC_PRECOMPUTE(1),.RS_COMPARISON_PRECOMPUTE(1),.RS_PC_PRECOMPUTE(1),.ALU_PRED_TARGET_CLASS_COMPARE(1),.ISSUE_PIPELINE(ISSUE_STAGE),.PRF_VALUE_SRAM(1),.PRF_READ_MUX_IMPL(1),.CHECKPOINT_IMPL(1),.RAT_RECOVERY_IMPL(1),
            .LOCAL_EXEC_RECOVERY(1),.RECOVERY_DIRECT_APPLY(DIRECT),.RECOVERY_ROB_CREDIT(1),
            .ROB_RECOVERY_PENDING_OWNER(1),.ROB_RECOVERY_WINDOW_OWNER(1),.MDU_OWNED_STEP(1),.LSQ_QUALIFIED_ADDRESS_WRITE(1),.RS_OCCUPANCY_DELTA_SELECT(1),.MDU_QUALIFIED_ISSUE_CLASS(1),.LSQ_INVALID_PAYLOAD_PRELOAD(1),.LSQ_QUALIFIED_METADATA_WRITE(0),.LSQ_REPORT_RANGE_CARRY_SELECT(policy),.RS_MDU_CLASS_PRESELECT(policy && !ISSUE_STAGE),.RS_ALLOC_STATIC_WRITE(1),.DISPATCH_PIPELINE(1),.DISPATCH_ELASTIC(1),.LSQ_ALLOC_SLOT_PRESELECT(1),.LSQ_ALLOC_PAYLOAD_PRESELECT(1),.LSQ_PHASED_DATA_OWNER(1),.LSQ_PHASED_DIRECT_WRITE_EVENTS(1),.LSQ_PHASED_ALLOC_EXCLUSIVE(1),.BRANCH_CAPTURE_REDIRECT_READY(1),.BRANCH_CAPTURE_PHASE_VALID(1),.BRANCH_CAPTURE_RESULT_OWNER(1),.EARLY_FRONT_REDIRECT(1),.ROB_COMPLETION_COMMIT_BYPASS(1),
            .COMPLETION_BYPASS(2),.COMPLETION_SOURCE_STATE_QUERY(2),
            .LSQ_ROB_QUERY_PREDECODE(1),.LOAD_COMPLETION_BYPASS(2),.LOAD_WAKE_BYPASS(1),.LSQ_SAVED_REPORT_PRIORITY(1),
            .LSQ_HEAD_LOAD_IDENTITY_QUERY(1),.LSQ_HELD_LOAD_IDENTITY_QUERY(DIRECT),
            .LSQ_HEAD_STORE_ACK_BYPASS(1),.LSQ_STORE_ACK_SOURCE_QUERY(1),.LSQ_HEAD_LOAD_PACKET_PRESELECT(1)) dut (
            .clk_i(clk),.reset_i(reset),.flush_i(flush),
            .trace_valid_i(trace_valid),.trace_ready_o(ready[policy]),.trace_pc_i(pc),
            .trace_inst_i(64'b0),.trace_op_i(op),.trace_imm_i(imm),.trace_rd_i(rd),
            .trace_rs1_i(source1),.trace_rs2_i(source2),.trace_rd_we_i(rdwe),
            .trace_rs1_used_i(isbranch|isstore|used1),.trace_rs2_used_i(isbranch|isstore|used2),
            .trace_is_load_i(isload),.trace_is_store_i(isstore),.trace_is_branch_i(isbranch),
            .trace_is_halt_i(2'b0),.trace_is_error_i(2'b0),.trace_mem_size_i(mem_size),
            .trace_mem_unsigned_i(2'b0),.trace_store_data_i(256'b0),
            .trace_pred_taken_i(2'b0),.trace_pred_target_i(64'b0),
            .trace_pred_kind_i(4'b0101),.trace_pred_metadata_i(32'b0),
            .dcache_req_valid_o(req_valid[policy]),.dcache_req_ready_i(1'b1),
            .dcache_req_is_load_o(req_load[policy]),.dcache_req_addr_o(req_addr[policy]),
            .dcache_req_lsq_tag_o(req_tag[policy]),.dcache_req_mask_o(req_mask[policy]),.dcache_req_wdata_o(req_data[policy]),
            .dcache_resp_valid_i(resp_valid),.dcache_resp_ready_o(resp_ready[policy]),
            .dcache_resp_lsq_tag_i(held_load_tag),.dcache_resp_query_valid_i(2'b0),
            .dcache_resp_query_tags_i(32'b0),.dcache_resp_addr_i(32'h20),
            .dcache_resp_line_data_i(128'b0),.dcache_resp_word_data_i(32'h12345678),
            .dcache_resp_line_valid_i(1'b0),.dcache_resp_error_i(resp_error),
            .dcache_store_ack_valid_i(ack_valid),.dcache_store_ack_lsq_tag_i(held_store_tag),
            .dcache_store_ack_error_i(1'b0),.store_ack_query_valid_i({ack_valid,1'b0}),
            .store_ack_query_tag_i({held_store_tag,16'b0}),.commit_ready_i(commit_ready),
            .commit_valid_o(commit_valid[policy]),.commit_pc_o(commit_pc[policy]),
            .commit_rd_we_o(commit_rdwe[policy]),.commit_value_o(commit_value[policy]),
            .commit_tag_o(commit_tag[policy]),.redirect_valid_o(redirect[policy]),
            .redirect_pc_o(redirect_pc[policy]),.halted_o(halted[policy]),.error_o(error[policy]));
    end endgenerate
    always @(posedge clk) if(!reset && !g_backend[0].dut.rs.flush_valid_i) begin
        count_delta_edges=count_delta_edges+1;
        if(g_backend[0].dut.rs.issue_fire_count>=0 && g_backend[0].dut.rs.issue_fire_count<=2)
            count_delta_seen[g_backend[0].dut.rs.issue_fire_count]=1'b1;
    end
    always @(negedge clk) begin
        #2;
        if(!reset) begin
            assert(g_backend[0].dut.rs.occupancy_o===g_backend[1].dut.rs.occupancy_o)
                else $fatal(1,"RS count delta changed saved occupancy direct=%0d",DIRECT);
            assert({ready[0],commit_valid[0],req_valid[0],resp_ready[0],redirect[0],halted[0],error[0]}==
                   {ready[1],commit_valid[1],req_valid[1],resp_ready[1],redirect[1],halted[1],error[1]})
                else $fatal(1,"RS count / MDU class changed a public handshake/cycle, direct=%0d",DIRECT);
            for(lane=0;lane<BW;lane=lane+1) if(commit_valid[0][lane])
                assert({commit_pc[0][lane*32+:32],commit_value[0][lane*32+:32],commit_rdwe[0][lane],commit_tag[0][lane*TW+:TW]}==
                       {commit_pc[1][lane*32+:32],commit_value[1][lane*32+:32],commit_rdwe[1][lane],commit_tag[1][lane*TW+:TW]})
                    else $fatal(1,"RS count / MDU class changed valid commit packet");
            if(req_valid[0]) assert({req_load[0],req_addr[0],req_tag[0],req_mask[0],req_data[0]}=={req_load[1],req_addr[1],req_tag[1],req_mask[1],req_data[1]});
            if(redirect[0]) assert(redirect_pc[0]==redirect_pc[1]);
            assert({g_backend[0].dut.branch_pending,g_backend[0].dut.rob_head,
                    g_backend[0].dut.rob_tail,g_backend[0].dut.rob_occupancy,g_backend[0].dut.rob_entry_valid,
                    g_backend[0].dut.rob_entry_generation,g_backend[0].dut.free_bitmap_state}==
                   {g_backend[1].dut.branch_pending,g_backend[1].dut.rob_head,
                    g_backend[1].dut.rob_tail,g_backend[1].dut.rob_occupancy,g_backend[1].dut.rob_entry_valid,
                    g_backend[1].dut.rob_entry_generation,g_backend[1].dut.free_bitmap_state})
                else $fatal(1,"RS count / MDU class changed row ownership/allocator state");
        end
    end
    always @(posedge clk) if(!reset) begin
        ack_valid<=req_valid[0] && !req_load[0];
        if(req_valid[0]) begin
            if(req_load[0]) begin
                assert(req_addr[0]==32'h20) else $fatal(1,"Unexpected load request");
                held_load_tag<=req_tag[0];held_load_seen<=1;read_count=read_count+1;
            end else begin
                case(stores_seen)
                    0:assert(req_addr[0]==32'h30 && req_mask[0]==16'h0001);
                    1:assert(req_addr[0]==32'h32 && req_mask[0]==16'h000c);
                    2:assert(req_addr[0]==32'h34 && req_mask[0]==16'h00f0);
                    default:$fatal(1,"Unexpected STORE request");
                endcase
                assert(req_data[0]==0);held_store_tag<=req_tag[0];stores_seen=stores_seen+1;
            end
        end
        for(integer n=0;n<BW;n=n+1)
            if(g_backend[1].dut.lsq_load_complete_valid && g_backend[1].dut.lsq_load_complete_ready &&
               g_backend[1].dut.raw_rs_issue_valid[n] &&
               g_backend[1].dut.raw_rs_issue_op[n*6 +: 6]==`RV32IM_OP_BNE) begin
                assert(g_backend[1].dut.raw_rs_issue_src1[n*32 +: 32]==32'h12345678);
                load_branch_wakes=load_branch_wakes+1;
            end
        if(|g_backend[1].dut.rob_wb_valid) state_samples=state_samples+1;
        if(g_backend[1].dut.completion_source_masks[2] ||
           g_backend[1].dut.completion_source_masks[6]) mdu_samples=mdu_samples+1;
        if(resp_valid && resp_error) begin
            assert(g_backend[0].dut.lsq_load_complete_error &&
                   g_backend[1].dut.lsq_load_complete_error);
            assert(!commit_valid[0][0] || commit_pc[0][0 +: 32]!=32'h1500)
                else $fatal(1,"Error LOAD committed on its response edge");
        end
        if(commit_valid[0][0] && commit_pc[0][0 +: 32]==32'h1500) begin
            assert(g_backend[0].dut.rob.head_ready[0] && g_backend[0].dut.rob.head_error[0] &&
                   g_backend[1].dut.rob.head_ready[0] && g_backend[1].dut.rob.head_error[0])
                else $fatal(1,"Error terminal record lacks registered error state");
        end
        if(g_backend[1].dut.branch_capture_write) begin
            captures=captures+1;
            if(captures==1) first_branch_tag=g_backend[1].dut.branch_capture_next[
                g_backend[1].dut.BRANCH_CAPTURE_WIDTH-1 -: TW];
        end
        if(g_backend[1].dut.rob_recovery_preview) previews=previews+1;
        if(g_backend[1].dut.rob_recovery_accept_source) applies=applies+1;
        if(g_backend[1].dut.branch_pending) begin
            pending_edges=pending_edges+1;
            window_checks=window_checks+1;
            assert(g_backend[0].dut.rob.recovery_found==g_backend[1].dut.rob.recovery_found &&
                   g_backend[0].dut.rob.chosen_age==g_backend[1].dut.rob.chosen_age &&
                   g_backend[0].dut.rob.chosen_slot==g_backend[1].dut.rob.chosen_slot &&
                   g_backend[0].dut.rob.recovery_preview_kill==g_backend[1].dut.rob.recovery_preview_kill)
                else $fatal(1,"Window ownership changed recovery selection or kill data");
            if(g_backend[1].dut.rob.chosen_age==0) window_head_checks=window_head_checks+1;
            else window_older_checks=window_older_checks+1;
        end
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
        source1={5'd0,5'd1};
        send(3,{32'h100c,32'h1008},{`RV32IM_OP_ADDI,`RV32IM_OP_BNE},
            {32'hbad,32'h40},{5'd3,5'd0},2'b10,0,2'b01);
        source1=0;
        // A real renamed LOAD wake makes the dependent BNE ready.
        for(timeout_count=0;timeout_count<30 && !held_load_seen;timeout_count=timeout_count+1) tick;
        if(!held_load_seen || read_count!=1) $fatal(1,"Older delayed load was not retained exactly once");
        @(negedge clk);resp_valid=1;tick;@(negedge clk);resp_valid=0;
        wait_pending;
        // Presents actual new work across apply, including optional direct
        // recovery allocation credits; staged mode preserves its hold.
        send(1,64'h1048,{6'b0,`RV32IM_OP_ADDI},64'd7,10'd3,1,0,0);
        commit_ready=1;
        wait_commits;
        if(captures!=1 || applies!=1 || previews==0 || pending_edges<(DIRECT?1:2))
            $fatal(1,"Recovery lifecycle was not exercised");
        // Five retained arithmetic points, using real renamed operands. The ADD
        // follows its two-lane producer bundle without waiting for commit.
        expect_packet(32'h1080,32'hffffffff,1);expect_packet(32'h1084,1,1);
        send(3,{32'h1084,32'h1080},{`RV32IM_OP_ADDI,`RV32IM_OP_ADDI},
            {32'd1,32'hffffffff},{5'd7,5'd6},3,0,0);
        source1={5'd0,5'd6};source2={5'd0,5'd7};used1=1;used2=1;
        expect_packet(32'h1088,0,1);
        send(1,64'h1088,{6'b0,`RV32IM_OP_ADD},0,10'd8,1,0,0);
        source1={5'd0,5'd7};source2={5'd0,5'd6};
        expect_packet(32'h108c,2,1);
        send(1,64'h108c,{6'b0,`RV32IM_OP_SUB},0,10'd9,1,0,0);
        source1={5'd0,5'd6};source2=0;used2=0;
        expect_packet(32'h1090,32'hfffffffe,1);
        send(1,64'h1090,{6'b0,`RV32IM_OP_ADDI},64'hffffffff,10'd10,1,0,0);
        source1=0;source2=0;used1=0;used2=0;
        wait_commits;
        // Four real compare results: signed/unsigned disagreement and a
        // sign-extended immediate. Compare both lanes and original commit data.
        source1={5'd6,5'd6};source2={5'd7,5'd7};used1=3;used2=3;
        expect_packet(32'h10a0,1,1);expect_packet(32'h10a4,0,1);
        send(3,{32'h10a4,32'h10a0},{`RV32IM_OP_SLTU,`RV32IM_OP_SLT},0,{5'd12,5'd11},3,0,0);
        source1={5'd7,5'd6};source2=0;used2=0;
        expect_packet(32'h10a8,1,1);expect_packet(32'h10ac,1,1);
        send(3,{32'h10ac,32'h10a8},{`RV32IM_OP_SLTIU,`RV32IM_OP_SLTI},{32'hffffffff,32'b0},{5'd14,5'd13},3,0,0);
        wait_commits;source1=0;source2=0;used1=0;used2=0;
        // Two real AUIPC results and a JAL link exercise row-local PC math,
        // full-width wrap, negative immediate and unchanged branch capture.
        expect_packet(32'hfffffffc,4,1);expect_packet(32'h10b4,32'h10b3,1);
        send(3,{32'h10b4,32'hfffffffc},{`RV32IM_OP_AUIPC,`RV32IM_OP_AUIPC},
            {32'hffffffff,32'd8},{5'd16,5'd15},3,0,0);
        wait_commits;
        expect_packet(32'h10b8,32'h10bc,1);
        send(1,64'h10b8,{6'b0,`RV32IM_OP_JAL},64'h40,10'd17,1,0,1);
        wait_commits;
        // Wrap and reuse all eight ROB rows with the original complete tags.
        for(i=0;i<8;i=i+1) begin
            expect_packet(32'h1100+i*4,(i==3)?32'b0:32'(10+i),1);
            send(1,64'(32'h1100+i*4),{6'b0,(i==3)?`RV32IM_OP_MUL:`RV32IM_OP_ADDI},64'(10+i),10'd4,1,0,0);
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
        // Reacquire a real nonzero base after reset. Three STORE addresses
        // exercise full-width wrapping arithmetic and the unchanged LSQ packet.
        commit_ready=1;expect_packet(32'h13f0,32'hffffffff,1);
        send(1,64'h13f0,{6'b0,`RV32IM_OP_ADDI},64'hffffffff,10'd6,1,0,0);
        wait_commits;source1={5'd0,5'd6};
        // Three access sizes reach ordinary completion and buffered STORE
        // admission, with real ACKs; compare the exact public masks/words.
        commit_ready=1;
        expect_packet(32'h1400,0,0);mem_size=4'b1000;
        send(1,64'h1400,{6'b0,`RV32IM_OP_SB},64'h31,0,0,0,0);wait_commits;
        expect_packet(32'h1404,0,0);mem_size=4'b1001;
        send(1,64'h1404,{6'b0,`RV32IM_OP_SH},64'h33,0,0,0,0);wait_commits;
        expect_packet(32'h1408,0,0);mem_size=4'b1010;
        send(1,64'h1408,{6'b0,`RV32IM_OP_SW},64'h35,0,0,0,0);wait_commits;
        for(timeout_count=0;timeout_count<30 && stores_seen!=3;timeout_count=timeout_count+1) tick;
        if(stores_seen!=3) $fatal(1,"STORE size sample did not drain");
        repeat(3) tick;
        source1=0;source2=0;
        // An error on the head-return edge must retain the original precise
        // error and block same-edge commit, then emit the original registered
        // terminal commit record before error_o; no fabricated table data.
        expect_packet(32'h1500,32'h12345678,1);
        send(1,64'h1500,{6'b0,`RV32IM_OP_LW},64'h20,10'd5,1,1,0);
        for(timeout_count=0;timeout_count<30 && read_count!=2;timeout_count=timeout_count+1) tick;
        if(read_count!=2) $fatal(1,"Error LOAD request absent");
        @(negedge clk);resp_valid=1;resp_error=1;tick;@(negedge clk);resp_valid=0;
        for(timeout_count=0;timeout_count<30 && !error[0];timeout_count=timeout_count+1) tick;
        if(error!=2'b11 || state_samples<12 || received!=expected || mdu_samples==0 || load_branch_wakes==0) $fatal(1,"Precise error/state selection not exercised");
        // Reset cancels its pending owner before the !reset monitor edge.
        // Three sampled owners cover normal BNE, JAL and whole-flush cases.
        $display("Window sample direct=%0d checks=%0d at_head=%0d retained_older=%0d",
                 DIRECT,window_checks,window_head_checks,window_older_checks);
        if(window_checks<3 || window_head_checks==0 || window_older_checks==0)
            $fatal(1,"Pending recovery did not cover head and older-retained window positions");
        done=1;
        if(count_delta_seen!=3'b111 || count_delta_edges<10)
            $fatal(1,"Missing real normal count0/1/2 coverage seen=%b edges=%0d",count_delta_seen,count_delta_edges);
        $display("COUNTS: direct=%0d count0/1/2=%b edges=%0d",DIRECT,count_delta_seen,count_delta_edges);
        $display("PASS: invalid LSQ private preload shared backend direct=%0d captures=%0d previews=%0d source_accepts=%0d load_branch_wakes=%0d",DIRECT,captures,previews,applies,load_branch_wakes);
    end
    always @(posedge clk) begin
        #1;
        for(integer row=0;row<4;row=row+1) begin
            assert(g_backend[0].dut.lsq.valid_mem[row]===g_backend[1].dut.lsq.valid_mem[row]) else $fatal(1,"Metadata owner changed valid state");
            assert(g_backend[0].dut.lsq.load_mem[row]===g_backend[1].dut.lsq.load_mem[row]) else $fatal(1,"Metadata owner changed load state");
            assert(g_backend[0].dut.lsq.store_mem[row]===g_backend[1].dut.lsq.store_mem[row]) else $fatal(1,"Metadata owner changed store state");
            assert(g_backend[0].dut.lsq.retired_mem[row]===g_backend[1].dut.lsq.retired_mem[row]) else $fatal(1,"Metadata owner changed retired state");
            assert(g_backend[0].dut.lsq.generation_mem[row]===g_backend[1].dut.lsq.generation_mem[row]) else $fatal(1,"Metadata owner changed generation state");
            assert(g_backend[0].dut.lsq.generation_next_mem[row]===g_backend[1].dut.lsq.generation_next_mem[row]) else $fatal(1,"Metadata owner changed generation_next state");
            assert(g_backend[0].dut.lsq.size_mem[row]===g_backend[1].dut.lsq.size_mem[row]) else $fatal(1,"Metadata owner changed size state");
            assert(g_backend[0].dut.lsq.unsigned_mem[row]===g_backend[1].dut.lsq.unsigned_mem[row]) else $fatal(1,"Metadata owner changed unsigned state");
            assert(g_backend[0].dut.lsq.addr_ready_mem[row]===g_backend[1].dut.lsq.addr_ready_mem[row]) else $fatal(1,"Metadata owner changed addr_ready state");
            assert(g_backend[0].dut.lsq.data_ready_mem[row]===g_backend[1].dut.lsq.data_ready_mem[row]) else $fatal(1,"Metadata owner changed data_ready state");
            assert(g_backend[0].dut.lsq.mask_mem[row]===g_backend[1].dut.lsq.mask_mem[row]) else $fatal(1,"Metadata owner changed mask state");
            assert(g_backend[0].dut.lsq.request_sent_mem[row]===g_backend[1].dut.lsq.request_sent_mem[row]) else $fatal(1,"Metadata owner changed request_sent state");
            assert(g_backend[0].dut.lsq.response_wait_mem[row]===g_backend[1].dut.lsq.response_wait_mem[row]) else $fatal(1,"Metadata owner changed response_wait state");
            assert(g_backend[0].dut.lsq.complete_mem[row]===g_backend[1].dut.lsq.complete_mem[row]) else $fatal(1,"Metadata owner changed complete state");
            assert(g_backend[0].dut.lsq.load_reported_mem[row]===g_backend[1].dut.lsq.load_reported_mem[row]) else $fatal(1,"Metadata owner changed load_reported state");
            assert(g_backend[0].dut.lsq.complete_error_mem[row]===g_backend[1].dut.lsq.complete_error_mem[row]) else $fatal(1,"Metadata owner changed complete_error state");
            assert(g_backend[0].dut.lsq.forward_mask_mem[row]===g_backend[1].dut.lsq.forward_mask_mem[row]) else $fatal(1,"Metadata owner changed forward_mask state");
            assert(g_backend[0].dut.lsq.store_commit_mem[row]===g_backend[1].dut.lsq.store_commit_mem[row]) else $fatal(1,"Metadata owner changed store_commit state");
            assert(g_backend[0].dut.lsq.store_ack_mem[row]===g_backend[1].dut.lsq.store_ack_mem[row]) else $fatal(1,"Metadata owner changed store_ack state");
            assert(g_backend[0].dut.lsq.store_ack_error_mem[row]===g_backend[1].dut.lsq.store_ack_error_mem[row]) else $fatal(1,"Metadata owner changed store_ack_error state");
        end
    end
endmodule
module rv32_range_carry_mdu_control_tb;
    wire staged_done,direct_done;
    rv32_range_carry_mdu_control_fixture #(.DIRECT(0),.ISSUE_STAGE(1)) staged (.done(staged_done));
    rv32_range_carry_mdu_control_fixture #(.DIRECT(1)) direct (.done(direct_done));
    wire plan_done,range_done;
    rv32_range_carry_mdu_plan_fixture planned(.done(plan_done));
    rv32_range_carry_probe range_sample (.done(range_done));
    initial begin wait(staged_done && direct_done && plan_done && range_done);#4;$display("PASS: limited paired range carry MDU control sample");$finish;end
    initial begin #6000;$fatal(1,"Pending owner sample timeout");end
endmodule

module rv32_range_carry_mdu_plan_fixture(output reg done=0);
    reg clk=0,reset=1,flush=0,recovery=0;
    always #5 clk=~clk;
    reg [1:0] plan=0,actual=0,loads=2'b01,stores=2'b10;
    reg [31:0] tags={16'h0049,16'h0041};
    reg [63:0] addresses={32'h28,32'h20},words={32'h76543210,32'h12345678};
    reg [11:0] destinations={6'd11,6'd9};
    reg ready=0,response=0;
    reg [15:0] response_tag=0,old_ticket=0;
    wire [1:0] fire[0:1];
    wire [31:0] allocation_tags[0:1];
    wire [4:0] occupancy[0:1];
    wire req_valid[0:1],req_load[0:1],req_store[0:1],response_ready[0:1];
    wire [31:0] req_address[0:1];
    wire [15:0] req_tag[0:1],req_rob[0:1],req_mask[0:1];
    wire [127:0] req_data[0:1];
    wire complete_valid[0:1],complete_error[0:1];
    wire [31:0] complete_value[0:1];
    wire [15:0] complete_tag[0:1],complete_lsq[0:1];
    wire [5:0] complete_phys[0:1];
    integer held_edges=0,plan_edges=0,requests=0,limit;
    for(genvar mode=0;mode<2;mode=mode+1) begin:g_policy
        rv32_lsq #(.BE_WIDTH(2),.LSQ_ENTRIES(16),.ROB_ENTRIES(8),.TAG_WIDTH(16),.ROB_TAG_WIDTH(16),
            .PHYS_ADDR_WIDTH(6),.RELEASE_CREDITS(0),.REQUEST_PIPELINE(1),
            .PHASED_DATA_OWNER(1),.PHASED_DIRECT_WRITE_EVENTS(1),.PHASED_ALLOC_EXCLUSIVE(1),
            .QUALIFIED_ADDRESS_WRITE(1),.ALLOC_SLOT_PRESELECT(1),.ALLOC_PAYLOAD_PRESELECT(1),
            .INVALID_PAYLOAD_PRELOAD(1),.QUALIFIED_METADATA_WRITE(0),.REPORT_RANGE_CARRY_SELECT(mode)) dut (
            .clk_i(clk),.reset_i(reset),.flush_i(flush),.recovery_valid_i(recovery),
            .recovery_tag_i(16'h0041),.recovery_head_i(3'b0),.recovery_occupancy_i(16'd8),
            .retire_valid_i(2'b0),.retire_rob_tag_i(32'b0),.alloc_valid_i(actual),.alloc_plan_valid_i(plan),
            .alloc_is_load_i(loads),.alloc_is_store_i(stores),.alloc_rob_tag_i(tags),.alloc_phys_rd_i(destinations),
            .alloc_size_i(4'b1010),.alloc_unsigned_i(2'b0),.alloc_addr_valid_i(plan),.alloc_addr_i(addresses),
            .alloc_data_valid_i(plan),.alloc_store_data_i(words),.alloc_store_mask_i(8'b0),
            .alloc_fire_o(fire[mode]),.alloc_lsq_tag_o(allocation_tags[mode]),.occupancy_o(occupancy[mode]),
            .addr_update_valid_i(2'b0),.addr_update_tag_i(32'b0),.addr_update_i(64'b0),
            .data_update_valid_i(2'b0),.data_update_tag_i(32'b0),.data_update_i(64'b0),.data_mask_update_i(8'b0),
            .wakeup_valid_i(2'b0),.wakeup_tag_i(32'b0),.wakeup_value_i(64'b0),
            .early_addr_valid_i(1'b0),.early_addr_tag_i(16'b0),.early_addr_i(32'b0),
            .store_commit_valid_i(2'b0),.store_commit_rob_tag_i(32'b0),
            .dcache_req_valid_o(req_valid[mode]),.dcache_req_ready_i(ready),
            .dcache_req_is_load_o(req_load[mode]),.dcache_req_is_store_o(req_store[mode]),
            .dcache_req_addr_o(req_address[mode]),.dcache_req_lsq_tag_o(req_tag[mode]),.dcache_req_rob_tag_o(req_rob[mode]),
            .dcache_req_mask_o(req_mask[mode]),.dcache_req_wdata_o(req_data[mode]),
            .dcache_resp_valid_i(response),.dcache_resp_ready_o(response_ready[mode]),.dcache_resp_lsq_tag_i(response_tag),
            .dcache_resp_query_valid_i(2'b0),.dcache_resp_query_tags_i(32'b0),.dcache_resp_addr_i(32'h20),
            .dcache_resp_line_data_i(128'b0),.dcache_resp_word_data_i(32'hbad0f00d),.dcache_resp_line_valid_i(1'b0),
            .dcache_resp_error_i(1'b0),.dcache_store_ack_valid_i(1'b0),.dcache_store_ack_lsq_tag_i(16'b0),
            .dcache_store_ack_error_i(1'b0),.store_ack_query_valid_i(2'b0),.store_ack_query_tag_i(32'b0),
            .load_complete_valid_o(complete_valid[mode]),.load_complete_ready_i(1'b0),
            .load_complete_rob_tag_o(complete_tag[mode]),.load_complete_lsq_tag_o(complete_lsq[mode]),
            .load_complete_value_o(complete_value[mode]),.load_complete_error_o(complete_error[mode]),
            .load_complete_phys_rd_o(complete_phys[mode]),.report_recovery_packet_i(10'b0));
    end
    for(genvar row=0;row<16;row=row+1) begin:g_live_compare
        always @(negedge clk) if(!reset) begin
            assert(g_policy[0].dut.valid_mem[row]===g_policy[1].dut.valid_mem[row] &&
                g_policy[0].dut.generation_mem[row]===g_policy[1].dut.generation_mem[row])
                else $fatal(1,"Preload changes actual valid/GEN row=%0d",row);
            if(g_policy[0].dut.valid_mem[row])
                assert(g_policy[0].dut.addr_mem[row]===g_policy[1].dut.addr_mem[row] &&
                    g_policy[0].dut.phased_word[row]===g_policy[1].dut.phased_word[row] &&
                    g_policy[0].dut.rob_tag_mem[row]===g_policy[1].dut.rob_tag_mem[row] &&
                    g_policy[0].dut.physical_destinations[row*6 +: 6]===g_policy[1].dut.physical_destinations[row*6 +: 6])
                    else $fatal(1,"Live payload differs row=%0d",row);
        end
    end
    always @(negedge clk) if(!reset) begin
        assert({fire[0],allocation_tags[0],occupancy[0],req_valid[0],req_load[0],req_store[0],req_address[0],
                req_tag[0],req_rob[0],req_mask[0],req_data[0],response_ready[0],complete_valid[0],complete_tag[0],
                complete_lsq[0],complete_value[0],complete_error[0],complete_phys[0]}===
               {fire[1],allocation_tags[1],occupancy[1],req_valid[1],req_load[1],req_store[1],req_address[1],
                req_tag[1],req_rob[1],req_mask[1],req_data[1],response_ready[1],complete_valid[1],complete_tag[1],
                complete_lsq[1],complete_value[1],complete_error[1],complete_phys[1]})
            else $fatal(1,"Planned preload changes raw public packet/cycle");
        if(|plan && !(|actual)) plan_edges=plan_edges+1;
        if(req_valid[0] && !ready) held_edges=held_edges+1;
    end
    always @(posedge clk) if(!reset && req_valid[0] && ready) begin
        requests=requests+1;if(requests==1) old_ticket=req_tag[0];
    end
    initial begin
        repeat(3) @(negedge clk);reset=0;plan=3;
        repeat(3) @(negedge clk);
        assert(occupancy[0]==0 && fire[0]==0 && !req_valid[0]) else $fatal(1,"Plan invents admission");
        addresses={32'h38,32'h30};words={32'hfedcba98,32'h89abcdef};destinations={6'd17,6'd13};
        repeat(2) @(negedge clk);actual=3;@(negedge clk);actual=0;plan=0;
        repeat(4) @(negedge clk);ready=1;limit=0;
        while(requests<1 && limit<20) begin @(negedge clk);limit=limit+1;end
        assert(requests==1) else $fatal(1,"Original LOAD not sent");
        recovery=1;@(negedge clk);recovery=0;repeat(2) @(negedge clk);
        flush=1;@(negedge clk);flush=0;
        plan=1;loads=1;stores=0;tags={16'b0,16'h0081};addresses={32'b0,32'h20};
        repeat(3) @(negedge clk);actual=1;@(negedge clk);actual=0;plan=0;
        limit=0;while(requests<2 && limit<20) begin @(negedge clk);limit=limit+1;end
        assert(requests==2 && g_policy[0].dut.generation_mem[0]!=old_ticket[7 +: 9])
            else $fatal(1,"Full generation slot reuse not observed");
        response_tag=old_ticket;response=1;@(negedge clk);response=0;repeat(3) @(negedge clk);
        assert(!complete_valid[0] && !g_policy[0].dut.complete_mem[0]) else $fatal(1,"Stale GEN response accepted");
        assert(plan_edges>=8 && held_edges>=3) else $fatal(1,"Plan/hold point not reached");
        $display("PASS: production16 planned payload point plan_only_edges=%0d held_edges=%0d sends=%0d",plan_edges,held_edges,requests);
        done=1;
    end
    initial begin #1500;if(!done)$fatal(1,"Planned preload point timeout");end
    always @(posedge clk) begin
        #1;
        for(integer row=0;row<16;row=row+1) begin
            assert(g_policy[0].dut.valid_mem[row]===g_policy[1].dut.valid_mem[row]) else $fatal(1,"Metadata owner changed valid state");
            assert(g_policy[0].dut.load_mem[row]===g_policy[1].dut.load_mem[row]) else $fatal(1,"Metadata owner changed load state");
            assert(g_policy[0].dut.store_mem[row]===g_policy[1].dut.store_mem[row]) else $fatal(1,"Metadata owner changed store state");
            assert(g_policy[0].dut.retired_mem[row]===g_policy[1].dut.retired_mem[row]) else $fatal(1,"Metadata owner changed retired state");
            assert(g_policy[0].dut.generation_mem[row]===g_policy[1].dut.generation_mem[row]) else $fatal(1,"Metadata owner changed generation state");
            assert(g_policy[0].dut.generation_next_mem[row]===g_policy[1].dut.generation_next_mem[row]) else $fatal(1,"Metadata owner changed generation_next state");
            assert(g_policy[0].dut.size_mem[row]===g_policy[1].dut.size_mem[row]) else $fatal(1,"Metadata owner changed size state");
            assert(g_policy[0].dut.unsigned_mem[row]===g_policy[1].dut.unsigned_mem[row]) else $fatal(1,"Metadata owner changed unsigned state");
            assert(g_policy[0].dut.addr_ready_mem[row]===g_policy[1].dut.addr_ready_mem[row]) else $fatal(1,"Metadata owner changed addr_ready state");
            assert(g_policy[0].dut.data_ready_mem[row]===g_policy[1].dut.data_ready_mem[row]) else $fatal(1,"Metadata owner changed data_ready state");
            assert(g_policy[0].dut.mask_mem[row]===g_policy[1].dut.mask_mem[row]) else $fatal(1,"Metadata owner changed mask state");
            assert(g_policy[0].dut.request_sent_mem[row]===g_policy[1].dut.request_sent_mem[row]) else $fatal(1,"Metadata owner changed request_sent state");
            assert(g_policy[0].dut.response_wait_mem[row]===g_policy[1].dut.response_wait_mem[row]) else $fatal(1,"Metadata owner changed response_wait state");
            assert(g_policy[0].dut.complete_mem[row]===g_policy[1].dut.complete_mem[row]) else $fatal(1,"Metadata owner changed complete state");
            assert(g_policy[0].dut.load_reported_mem[row]===g_policy[1].dut.load_reported_mem[row]) else $fatal(1,"Metadata owner changed load_reported state");
            assert(g_policy[0].dut.complete_error_mem[row]===g_policy[1].dut.complete_error_mem[row]) else $fatal(1,"Metadata owner changed complete_error state");
            assert(g_policy[0].dut.forward_mask_mem[row]===g_policy[1].dut.forward_mask_mem[row]) else $fatal(1,"Metadata owner changed forward_mask state");
            assert(g_policy[0].dut.store_commit_mem[row]===g_policy[1].dut.store_commit_mem[row]) else $fatal(1,"Metadata owner changed store_commit state");
            assert(g_policy[0].dut.store_ack_mem[row]===g_policy[1].dut.store_ack_mem[row]) else $fatal(1,"Metadata owner changed store_ack state");
            assert(g_policy[0].dut.store_ack_error_mem[row]===g_policy[1].dut.store_ack_error_mem[row]) else $fatal(1,"Metadata owner changed store_ack_error state");
        end
    end
endmodule

module rv32_range_carry_probe(output reg done=0);
    reg [3:0] head=0;
    reg [4:0] count=0;
    wire [15:0] mask;
    integer points=0;
    rv32_lsq_report_range_carry #(.ENTRIES(16),.SLOT_WIDTH(4),.COUNT_WIDTH(5)) dut (
        .head_i(head),.count_i(count),.range_o(mask));
    initial begin
        for(integer h=0;h<16;h=h+1) begin
            for(integer n=0;n<32;n=n+1) begin
                head=4'(h);count=5'(n);#1;
                for(integer row=0;row<16;row=row+1)
                    assert(mask[row]===(((row-h)&15)<n))
                        else $fatal(1,"Carry range mismatch head=%0d count=%0d row=%0d",h,n,row);
                points=points+1;
            end
        end
        assert(points==512);
        $display("PASS: full count carry range points=%0d",points);
        done=1;
    end
endmodule
