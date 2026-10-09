`timescale 1ns/1ps
`include "rv32im_defs.vh"
module rv32_target_class_compare_tb;
    reg clk=0,reset=1,flush=0,iv=0,consume=1;
    always #5 clk=~clk;
    reg [5:0] op=0;
    reg [31:0] pc=0,imm=0,lhs=0,rhs=0,target=0;
    reg predicted_taken=0;
    wire [3:0] ready,valid,redirect;
    wire [351:0] packets[0:3];
    integer points=0;
    for(genvar c=0;c<2;c=c+1) begin:g_compact
        for(genvar p=0;p<2;p=p+1) begin:g_policy
            localparam integer N=2*c+p;
            wire [31:0] value,btarget,rpc,addr,store_data,source_pc,pred_target;
            wire [5:0] phys;
            wire [15:0] tag;
            wire [3:0] epoch;
            wire rdwe,branch,taken,memory,load,store,mem_unsigned,pred_taken,saved_valid;
            wire [1:0] size,kind;
            rv32i_alu #(.TAG_WIDTH(16),.PHYS_ADDR_WIDTH(6),.ROB_ENTRIES(8),
                .COMPACT_PRED_TARGET(c),.PRED_TARGET_CLASS_COMPARE(p),.FORWARD_METADATA(1)) dut (
                .clk_i(clk),.reset_i(reset),.flush_i(flush),.recovery_packet_i(11'b0),
                .issue_valid_i(iv),.issue_cancel_i(1'b0),.issue_ready_o(ready[N]),
                .issue_op_i(op),.issue_pc_i(pc),.issue_imm_i(imm),.issue_arithmetic_i(32'b0),
                .issue_comparison_i(3'b0),.issue_src1_value_i(lhs),.issue_src2_value_i(rhs),
                .issue_store_data_i(32'b0),.issue_phys_rd_i(6'd7),.issue_rob_tag_i(16'h0001),
                .issue_epoch_i(4'b0),.issue_target_live_i(1'b1),.issue_pred_taken_i(predicted_taken),
                .issue_pred_target_i(target),.issue_pred_kind_i(2'b11),.issue_mem_size_i(2'b10),
                .issue_mem_unsigned_i(1'b0),.exec_valid_o(valid[N]),.exec_saved_valid_o(saved_valid),
                .exec_ready_i(consume),.exec_value_o(value),.exec_phys_rd_o(phys),.exec_rob_tag_o(tag),
                .exec_epoch_o(epoch),.exec_rd_we_o(rdwe),.exec_is_branch_o(branch),
                .exec_branch_taken_o(taken),.exec_branch_target_o(btarget),.exec_redirect_valid_o(redirect[N]),
                .exec_redirect_pc_o(rpc),.exec_is_memory_o(memory),.exec_is_load_o(load),.exec_is_store_o(store),
                .exec_mem_addr_o(addr),.exec_mem_size_o(size),.exec_mem_unsigned_o(mem_unsigned),
                .exec_store_data_o(store_data),.exec_source_pc_o(source_pc),.exec_pred_taken_o(pred_taken),
                .exec_pred_target_o(pred_target),.exec_pred_kind_o(kind),.live_tag_valid_i(1'b0),.live_tag_i(16'b0));
            assign packets[N]={value,phys,tag,epoch,rdwe,branch,taken,btarget,redirect[N],rpc,
                memory,load,store,addr,size,mem_unsigned,store_data,source_pc,pred_taken,pred_target,kind};
        end
    end
    task tick;begin @(posedge clk);#1;end endtask
    always @(negedge clk) if(!reset) begin
        assert(ready[0]==ready[1] && ready[2]==ready[3]);
        assert(valid[0]==valid[1] && valid[2]==valid[3]);
        if(valid[0]) assert(packets[0]==packets[1]);
        if(valid[2]) assert(packets[2]==packets[3]);
    end
    task point(input [5:0] o,input [31:0] ip,a,b,im,pt,input bit pred,e0,e1);
        begin
            @(negedge clk);op=o;pc=ip;lhs=a;rhs=b;imm=im;target=pt;predicted_taken=pred;iv=1;consume=1;
            #1;assert(ready==4'b1111);tick;
            assert(valid==4'b1111);
            assert(packets[0]==packets[1] && packets[2]==packets[3]);
            assert(redirect[0]==e0 && redirect[1]==e0 && redirect[2]==e1 && redirect[3]==e1)
                else $fatal(1,"Target class point failed index=%0d redirect=%b",points,redirect);
            points=points+1;
            @(negedge clk);iv=0;consume=0;tick;tick;
            assert(valid==4'b1111 && packets[0]==packets[1] && packets[2]==packets[3]);
            @(negedge clk);consume=1;tick;assert(valid==0);
        end
    endtask
    initial begin
        tick;tick;@(negedge clk);reset=0;
        point(`RV32IM_OP_BEQ,32'h80001000,32'h12345678,32'h12345678,32'h20,32'h80001020,1,0,0);
        point(`RV32IM_OP_BEQ,32'h80001000,1,1,32'h20,32'h80001024,1,1,0);
        point(`RV32IM_OP_BNE,32'h80001000,1,1,32'h20,32'h80001020,1,1,1);
        point(`RV32IM_OP_JAL,32'h80001000,0,0,32'h20,32'h80001020,1,0,0);
        point(`RV32IM_OP_JALR,32'h80001000,32'h80001000,0,3,32'h80001002,1,0,0);
        point(`RV32IM_OP_JALR,32'h80001000,32'h80001000,0,3,32'h80001003,1,1,1);
        point(`RV32IM_OP_JALR,32'h80001000,32'h80002000,0,3,32'h80001002,1,1,1);
        point(`RV32IM_OP_AUIPC,32'h80001000,0,0,32'h20,0,1,0,0);
        point(`RV32IM_OP_BEQ,32'hfffffffc,0,0,8,4,1,0,0);
        @(negedge clk);flush=1;tick;assert(valid==0);
        $display("PASS: limited paired target-class sample points=%0d",points);$finish;
    end
    initial begin #3000;$fatal(1,"Target class sample timeout");end
endmodule
