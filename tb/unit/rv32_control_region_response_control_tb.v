`timescale 1ns/1ps
`include "rv32im_defs.vh"
module rv32_control_region_response_backend_fixture #(parameter integer DIRECT=0,ISSUE_STAGE=0)(output reg done=0);
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
            .ROB_RECOVERY_PENDING_OWNER(1),.ROB_RECOVERY_WINDOW_OWNER(1),.MDU_OWNED_STEP(1),.LSQ_QUALIFIED_ADDRESS_WRITE(1),.RS_OCCUPANCY_DELTA_SELECT(1),.MDU_QUALIFIED_ISSUE_CLASS(1),.LSQ_INVALID_PAYLOAD_PRELOAD(1),.LSQ_QUALIFIED_METADATA_WRITE(0),.LSQ_REPORT_RANGE_CARRY_SELECT(1),.RS_MDU_CLASS_PRESELECT(!ISSUE_STAGE),.LSQ_RESPONSE_WORD_PRESELECT(policy),.LSQ_RESPONSE_QUERY_PREDECODE(1),.LSQ_RESPONSE_SOURCE_QUERY(1),.RS_ALLOC_STATIC_WRITE(1),.DISPATCH_PIPELINE(1),.DISPATCH_ELASTIC(1),.LSQ_ALLOC_SLOT_PRESELECT(1),.LSQ_ALLOC_PAYLOAD_PRESELECT(1),.LSQ_PHASED_DATA_OWNER(1),.LSQ_PHASED_DIRECT_WRITE_EVENTS(1),.LSQ_PHASED_ALLOC_EXCLUSIVE(1),.BRANCH_CAPTURE_REDIRECT_READY(1),.BRANCH_CAPTURE_PHASE_VALID(1),.BRANCH_CAPTURE_RESULT_OWNER(1),.EARLY_FRONT_REDIRECT(1),.ROB_COMPLETION_COMMIT_BYPASS(1),
            .COMPLETION_BYPASS(2),.COMPLETION_SOURCE_STATE_QUERY(2),
            .LSQ_ROB_QUERY_PREDECODE(1),.LOAD_COMPLETION_BYPASS(2),.LOAD_WAKE_BYPASS(1),.LSQ_SAVED_REPORT_PRIORITY(1),
            .LSQ_HEAD_LOAD_IDENTITY_QUERY(1),.LSQ_HELD_LOAD_IDENTITY_QUERY(0),.LSQ_REPORT_RECOVERY_PREQUALIFY(1),.LSQ_REPORT_RECOVERY_CIRCULAR_COMPARE(1),
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
            .dcache_resp_lsq_tag_i(held_load_tag),.dcache_resp_query_valid_i({1'b0,resp_valid}),
            .dcache_resp_query_tags_i({16'b0,held_load_tag}),.dcache_resp_addr_i(32'h20),
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
            assert(g_backend[0].dut.lsq.payload_response_value===g_backend[1].dut.lsq.payload_response_value &&
                   g_backend[0].dut.lsq.response_match_rows===g_backend[1].dut.lsq.response_match_rows)
                else $fatal(1,"Prepared WORD response changed raw formatter/default-row/full identity");
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
`timescale 1ns/1ps
// One finite real-transaction pair; all state is allocated by public requests/refills.
module rv32_control_region_response_cache_fixture(output reg done=0);
    reg clk=0,reset=1;
    always #5 clk=~clk;
    reg [3:0] epoch=4'h9;
    reg req_valid=0,resp_ready=0,mem_gate=0,reply_valid=0,reply_error=0;
    reg [31:0] req_pc=0,reply_addr=0;
    reg [7:0] reply_id=0;
    reg [127:0] reply_data=0;
    wire [1:0] req_ready,resp_valid,resp_error,mem_valid,mem_ready;
    wire [31:0] resp_pc[0:1],resp_addr[0:1],mem_addr[0:1];
    wire [127:0] resp_data[0:1];
    wire [3:0] resp_epoch[0:1];
    wire [7:0] mem_id[0:1];
    wire [4:0] events[0:1];
    localparam [127:0] NOPS={4{32'h00000013}};
    localparam [127:0] JUMP={{3{32'h00000013}},32'h7000006f}; // 0x100 -> 0x800
    reg [31:0] issued_addr[0:15];
    reg [7:0] issued_id[0:15];
    integer issued=0,replies=0,held=0,three_classes=0,stale_checked=0,step=0,n,slot;
    integer demand_count,control_count,sequential_count;
    generate for(genvar policy=0;policy<2;policy=policy+1) begin:g_pair
        rv32_icache_nonblocking #(.EPOCH_WIDTH(4),.MSHR_ENTRIES(8),.CLASS_SEND_SELECT(1),.CONTROL_TARGET_PREFIX(1),.QUERY_DOMAINS(16),.CONTROL_REGION_PREQUERY(policy),
            .MSHR_STATIC_WRITES(1),.MSHR_STATE_BANKS(1),.CACHE_LINES(128),.CACHE_WAYS(2),
            .TAG_MATCH_PARALLEL(1),.TAG_REGION_BITS(12),.LOCAL_RESPONSE_READY(1),
            .REQUEST_PIPELINE(1),.OWNER_PAYLOAD_SELECT(1),.LOOP_BUFFER_LINES(16),.LOOP_BUFFER_SRAM(1),
            .NEXT_LINE_PREFETCH(1),.PREFETCH_DISTANCE(7)) dut (
            .clk_i(clk),.reset_i(reset),.current_epoch_i(epoch),
            .if_req_valid_i(req_valid),.if_req_ready_o(req_ready[policy]),.if_req_pc_i(req_pc),.if_req_epoch_i(epoch),
            .if_resp_valid_o(resp_valid[policy]),.if_resp_ready_i(resp_ready),.if_resp_pc_o(resp_pc[policy]),
            .if_resp_line_addr_o(resp_addr[policy]),.if_resp_line_data_o(resp_data[policy]),
            .if_resp_epoch_o(resp_epoch[policy]),.if_resp_error_o(resp_error[policy]),
            .mem_req_valid_o(mem_valid[policy]),.mem_req_ready_i(mem_gate),
            .mem_req_line_addr_o(mem_addr[policy]),.mem_req_id_o(mem_id[policy]),
            .mem_resp_valid_i(reply_valid),.mem_resp_ready_o(mem_ready[policy]),
            .mem_resp_line_addr_i(reply_addr),.mem_resp_data_i(reply_data),.mem_resp_id_i(reply_id),
            .mem_resp_error_i(reply_error),.event_request_o(events[policy][0]),.event_hit_o(events[policy][1]),
            .event_miss_o(events[policy][2]),.event_refill_o(events[policy][3]),.event_stall_o(events[policy][4]));
    end endgenerate
    always @(posedge clk) if(!reset) begin
        if(req_ready[0]!==req_ready[1] || resp_valid[0]!==resp_valid[1] ||
           mem_valid[0]!==mem_valid[1] || mem_ready[0]!==mem_ready[1] || events[0]!==events[1] ||
           mem_addr[0]!==mem_addr[1] || mem_id[0]!==mem_id[1])
            $fatal(1,"Class pair public control/full raw request differs step=%0d",step);
        if(resp_valid[0] && {resp_pc[0],resp_addr[0],resp_data[0],resp_epoch[0],resp_error[0]} !==
                            {resp_pc[1],resp_addr[1],resp_data[1],resp_epoch[1],resp_error[1]})
            $fatal(1,"Class pair full instruction reply differs step=%0d",step);
        if(g_pair[0].dut.control_match_rows!==g_pair[1].dut.control_match_rows ||
           g_pair[0].dut.control_target_present!==g_pair[1].dut.control_target_present ||
           g_pair[0].dut.control_target!==g_pair[1].dut.control_target)
            $fatal(1,"Region prequery changed raw complete control query/presence");
        for(integer row=0;row<8;row=row+1) begin
            if({g_pair[0].dut.mshr_valid[row],g_pair[0].dut.mshr_sent[row],g_pair[0].dut.mshr_prefetch[row],g_pair[0].dut.mshr_control_prefetch[row]} !==
               {g_pair[1].dut.mshr_valid[row],g_pair[1].dut.mshr_sent[row],g_pair[1].dut.mshr_prefetch[row],g_pair[1].dut.mshr_control_prefetch[row]})
                $fatal(1,"Class pair MSHR lifecycle differs row=%0d",row);
            if(g_pair[0].dut.mshr_valid[row] &&
               {g_pair[0].dut.mshr_line[row],g_pair[0].dut.mshr_pc[row],g_pair[0].dut.mshr_txn_epoch[row],g_pair[0].dut.mshr_demand_epoch[row]} !==
               {g_pair[1].dut.mshr_line[row],g_pair[1].dut.mshr_pc[row],g_pair[1].dut.mshr_txn_epoch[row],g_pair[1].dut.mshr_demand_epoch[row]})
                $fatal(1,"Class pair full MSHR identity differs row=%0d",row);
        end
        if(mem_valid[0] && mem_gate) begin
            if(issued>=16) $fatal(1,"Unexpected repeated send");
            issued_addr[issued]=mem_addr[0];issued_id[issued]=mem_id[0];issued=issued+1;
        end
        if(resp_valid[0] && resp_ready) replies=replies+1;
        if(resp_valid[0] && !resp_ready) held=held+1;
    end
    task submit;
        input [31:0] address;
        begin
            @(negedge clk);req_pc=address;req_valid=1;
            #1;while(!req_ready[0]) begin @(negedge clk);#1;end
            @(negedge clk);req_valid=0;
            repeat(3) @(negedge clk);
        end
    endtask
    task send_one;
        input [31:0] address;
        input [3:0] expected_epoch;
        begin
            @(negedge clk);#1;
            if(!mem_valid[0] || mem_addr[0]!==address || mem_id[0][3:0]!==expected_epoch)
                $fatal(1,"Wrong class priority step=%0d wanted=%h got=%h id=%h",step,address,mem_addr[0],mem_id[0]);
            mem_gate=1;
            @(negedge clk);mem_gate=0;
        end
    endtask
    task return_line;
        input [31:0] address;
        input [127:0] data;
        input error;
        begin
            slot=-1;
            for(n=0;n<issued;n=n+1) if(issued_addr[n]==address) slot=n;
            if(slot<0) $fatal(1,"Fixture returning unsent line");
            @(negedge clk);reply_valid=1;reply_addr=address;reply_id=issued_id[slot];reply_data=data;reply_error=error;
            #1;while(!mem_ready[0]) begin @(negedge clk);#1;end
            @(negedge clk);reply_valid=0;reply_error=0;
        end
    endtask
    task expect_reply;
        input [31:0] address;
        input [127:0] data;
        input error;
        begin
            #1;while(!resp_valid[0]) begin @(negedge clk);#1;end
            if(resp_pc[0]!==address || resp_addr[0]!==address || resp_data[0]!==data ||
               resp_epoch[0]!==epoch || resp_error[0]!==error)
                $fatal(1,"Wrong architectural reply step=%0d pc=%h",step,resp_pc[0]);
        end
    endtask
    task consume;
        begin @(negedge clk);resp_ready=1;@(negedge clk);resp_ready=0;end
    endtask
    initial begin
        repeat(3) @(negedge clk);reset=0;
        step=1;submit(32'h100);repeat(8) @(negedge clk);
        send_one(32'h100,4'h9);return_line(32'h100,JUMP,0);expect_reply(32'h100,JUMP,0);
        repeat(3) @(negedge clk);
        if(!mem_valid[0] || mem_addr[0]!==32'h800) $fatal(1,"Control target did not outrank sequential traffic");
        consume;
        step=2;submit(32'h110);
        demand_count=0;control_count=0;sequential_count=0;
        for(n=0;n<8;n=n+1) if(g_pair[0].dut.mshr_valid[n] && !g_pair[0].dut.mshr_sent[n]) begin
            if(!g_pair[0].dut.mshr_prefetch[n]) demand_count=demand_count+1;
            else if(g_pair[0].dut.mshr_control_prefetch[n]) control_count=control_count+1;
            else sequential_count=sequential_count+1;
        end
        if(demand_count!=1 || control_count!=1 || sequential_count<2)
            $fatal(1,"Real three-class competition missing d=%0d c=%0d s=%0d",demand_count,control_count,sequential_count);
        three_classes=three_classes+1;
        send_one(32'h110,4'h9);send_one(32'h800,4'h9);send_one(32'h120,4'h9);
        return_line(32'h110,NOPS,0);expect_reply(32'h110,NOPS,0);
        repeat(3) @(negedge clk);consume;
        // Ordinary old-epoch rows disappear immediately; actual control rows survive.
        step=3;@(negedge clk);epoch=4'h3;
        #1;if(!g_pair[0].dut.mshr_valid[0] || !g_pair[0].dut.mshr_control_prefetch[0])
            $fatal(1,"Real old control ownership missing at redirect");
        submit(32'h900);send_one(32'h900,4'h3);
        return_line(32'h120,NOPS,0);repeat(2) @(negedge clk);
        if(resp_valid[0]) $fatal(1,"Stale sequential response became architectural reply");
        stale_checked=stale_checked+1;
        return_line(32'h800,NOPS,0);repeat(2) @(negedge clk);
        if(resp_valid[0]) $fatal(1,"Unpromoted control response became architectural reply");
        step=4;return_line(32'h900,NOPS,1);expect_reply(32'h900,NOPS,1);consume;
        if(replies!=3 || issued!=5 || held<6 || three_classes!=1 || stale_checked!=1)
            $fatal(1,"Incomplete finite coverage replies=%0d sends=%0d held=%0d",replies,issued,held);
        $display("PASS: finite I-cache control region pair sends=%0d replies=%0d held=%0d three_classes=%0d stale=%0d",issued,replies,held,three_classes,stale_checked);
        done=1;
    end
    initial begin #20000;$fatal(1,"Finite class send timeout step=%0d",step);end
endmodule

module rv32_response_word_format_probe(output reg done=0);
    reg [31:0] word_data=32'h8001ff80,forward_data=32'h017faa80;
    reg [3:0] mask=0;
    reg [1:0] size=0;
    reg uns=0;
    wire [31:0] value;
    reg [31:0] bits_mask,merged,expected;
    integer points=0;
    rv32_lsq_response_word_format dut (
        .word_i(word_data),.forward_i(forward_data),.mask_i(mask),.size_i(size),.unsigned_i(uns),.value_o(value));
    initial begin
        for(integer m=0;m<16;m=m+1)
            for(integer s=0;s<4;s=s+1)
                for(integer u=0;u<2;u=u+1) begin
                    mask=4'(m);size=2'(s);uns=1'(u);#1;
                    bits_mask={{8{mask[3]}},{8{mask[2]}},{8{mask[1]}},{8{mask[0]}}};
                    merged=(forward_data & bits_mask) | (word_data & ~bits_mask);
                    case(size)
                        0:expected=uns?{24'b0,merged[7:0]}:{{24{merged[7]}},merged[7:0]};
                        1:expected=uns?{16'b0,merged[15:0]}:{{16{merged[15]}},merged[15:0]};
                        default:expected=merged;
                    endcase
                    assert(value===expected) else $fatal(1,"Response word format mismatch mask=%0d size=%0d unsigned=%0d",m,s,u);
                    points=points+1;
                end
        assert(points==128);$display("PASS: raw response word format points=%0d",points);done=1;
    end
endmodule

module rv32_control_region_query_probe(output reg done=0);
    reg [127:0] candidates={32'hfffabc27,32'h80000400,32'h45600800,32'h12300fff};
    reg [3:0] grants=0;
    reg [23:0] prefixes=0;
    wire [31:0] views;
    reg [31:0] original_target;
    integer points=0,hit_count=0,misses=0;
    rv32_icache_control_region_query #(.REGION_BITS(12),.WAYS(2),.DOMAINS(16)) dut (
        .candidates_i(candidates),.grants_i(grants),.prefixes_i(prefixes),.matches_o(views));
    initial begin
        for(integer prefix_case=0;prefix_case<3;prefix_case=prefix_case+1) begin
            case(prefix_case)
                0:prefixes={12'hfff,12'h000};
                1:prefixes={12'h456,12'h123};
                default:prefixes={12'h800,12'habc};
            endcase
            for(integer selected=0;selected<5;selected=selected+1) begin
                grants=(selected==0)?4'b0:(4'(1)<<(selected-1));#1;
                original_target=0;
                for(integer lane=0;lane<4;lane=lane+1)
                    if(grants[lane]) original_target=original_target | candidates[lane*32 +: 32];
                for(integer way=0;way<2;way=way+1) begin
                    assert(views[way*16 +: 16]==={16{prefixes[way*12 +: 12]==original_target[31:20]}})
                        else $fatal(1,"Raw region query mismatch including absent target zero equality");
                    if(views[way*16]) hit_count=hit_count+1;else misses=misses+1;
                end
                points=points+1;
            end
        end
        assert(points==15 && hit_count>0 && misses>0);
        $display("PASS: raw control region points=%0d hit_count=%0d misses=%0d",points,hit_count,misses);done=1;
    end
endmodule

module rv32_control_region_response_control_tb;
    wire direct_done,staged_done,cache_done,word_done,region_done;
    rv32_control_region_response_backend_fixture #(.DIRECT(1)) direct (.done(direct_done));
    rv32_control_region_response_backend_fixture #(.DIRECT(0),.ISSUE_STAGE(1)) staged (.done(staged_done));
    rv32_control_region_response_cache_fixture cache_sample (.done(cache_done));
    rv32_response_word_format_probe word_sample (.done(word_done));
    rv32_control_region_query_probe region_sample (.done(region_done));
    initial begin
        wait(direct_done && staged_done && cache_done && word_done && region_done);#4;
        $display("PASS: limited paired control region response format sample");$finish;
    end
    initial begin #20000;$fatal(1,"Combined finite sample timeout");end
endmodule
