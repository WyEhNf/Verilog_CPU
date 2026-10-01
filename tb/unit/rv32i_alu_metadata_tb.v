`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Added metadata must not feed back into any original ALU result or handshake.
module rv32i_alu_metadata_tb #(parameter integer SHIFT_IMPL = 0);
    reg clk=0, reset=1, flush=0;
    always #5 clk=~clk;
    reg issue_valid=0, exec_ready=0, target_live=1, live_valid=0;
    reg [`RV32IM_OP_WIDTH-1:0] op=0;
    reg [31:0] pc=0, imm=0, src1=0, src2=0, store_data=0, pred_target=0;
    reg [15:0] tag=1, live_tag=1;
    reg [5:0] phys=0;
    reg [3:0] epoch=0;
    reg pred_taken=0, mem_unsigned=0;
    reg [1:0] pred_kind=0, mem_size=2;
    wire [1:0] ready, valid, rd_we, branch, taken, redirect, memory_op, load_op, store_op, unsigned_out;
    wire [31:0] value[0:1], target[0:1], redirect_pc[0:1], addr[0:1], data[0:1];
    wire [5:0] out_phys[0:1];
    wire [15:0] out_tag[0:1];
    wire [3:0] out_epoch[0:1];
    wire [1:0] size[0:1], out_pred_kind[0:1];
    wire [31:0] source_pc[0:1], out_pred_target[0:1];
    wire [1:0] out_pred_taken;
    genvar m;
    generate for(m=0;m<2;m=m+1) begin:g_unit
        rv32i_alu #(.TAG_WIDTH(16),.PHYS_ADDR_WIDTH(6),.SHIFT_IMPL(SHIFT_IMPL),.FORWARD_METADATA(m)) alu(
            .clk_i(clk),.reset_i(reset),.flush_i(flush),.issue_valid_i(issue_valid),.issue_ready_o(ready[m]),
            .issue_op_i(op),.issue_pc_i(pc),.issue_imm_i(imm),.issue_src1_value_i(src1),
            .issue_src2_value_i(src2),.issue_store_data_i(store_data),.issue_phys_rd_i(phys),
            .issue_rob_tag_i(tag),.issue_epoch_i(epoch),.issue_target_live_i(target_live),
            .issue_pred_taken_i(pred_taken),.issue_pred_target_i(pred_target),.issue_pred_kind_i(pred_kind),
            .issue_mem_size_i(mem_size),.issue_mem_unsigned_i(mem_unsigned),
            .exec_valid_o(valid[m]),.exec_ready_i(exec_ready),.exec_value_o(value[m]),
            .exec_phys_rd_o(out_phys[m]),.exec_rob_tag_o(out_tag[m]),.exec_epoch_o(out_epoch[m]),
            .exec_rd_we_o(rd_we[m]),.exec_is_branch_o(branch[m]),.exec_branch_taken_o(taken[m]),
            .exec_branch_target_o(target[m]),.exec_redirect_valid_o(redirect[m]),.exec_redirect_pc_o(redirect_pc[m]),
            .exec_is_memory_o(memory_op[m]),.exec_is_load_o(load_op[m]),.exec_is_store_o(store_op[m]),
            .exec_mem_addr_o(addr[m]),.exec_mem_size_o(size[m]),.exec_mem_unsigned_o(unsigned_out[m]),
            .exec_store_data_o(data[m]),.exec_source_pc_o(source_pc[m]),.exec_pred_taken_o(out_pred_taken[m]),
            .exec_pred_target_o(out_pred_target[m]),.exec_pred_kind_o(out_pred_kind[m]),
            .live_tag_valid_i(live_valid),.live_tag_i(live_tag)
        );
    end endgenerate
    reg [31:0] expected_pc=0, expected_pred_target=0;
    reg expected_pred_taken=0;
    reg [1:0] expected_pred_kind=0;
    integer checks=0, accepted=0, cycle;
    reg [31:0] random_state=32'h7a73c291;
    function [31:0] next_random;
        reg [31:0] x;
        begin
            x=random_state; x=x^(x<<13); x=x^(x>>17); x=x^(x<<5);
            random_state=x;
            next_random=x;
        end
    endfunction
    always @(posedge clk) begin
        if(reset || flush) begin
            expected_pc<=0; expected_pred_target<=0; expected_pred_taken<=0; expected_pred_kind<=0;
        end else if(!g_unit[0].alu.shift_busy &&
            !(g_unit[0].alu.result_valid_reg && live_valid &&
              (g_unit[0].alu.result_rob_tag_reg!=live_tag) && !exec_ready) &&
            ready[0] && issue_valid) begin
            expected_pc<=pc; expected_pred_target<=pred_target;
            expected_pred_taken<=pred_taken; expected_pred_kind<=pred_kind;
            accepted=accepted+1;
        end
    end
    always @(negedge clk) begin
        if(!reset) begin
            if({ready[0],valid[0],value[0],out_phys[0],out_tag[0],out_epoch[0],rd_we[0],branch[0],
                taken[0],target[0],redirect[0],redirect_pc[0],memory_op[0],load_op[0],store_op[0],
                addr[0],size[0],unsigned_out[0],data[0]} !==
               {ready[1],valid[1],value[1],out_phys[1],out_tag[1],out_epoch[1],rd_we[1],branch[1],
                taken[1],target[1],redirect[1],redirect_pc[1],memory_op[1],load_op[1],store_op[1],
                addr[1],size[1],unsigned_out[1],data[1]})
                $fatal(1,"ALU metadata changed an original output, shift=%0d",SHIFT_IMPL);
            if({source_pc[1],out_pred_target[1],out_pred_taken[1],out_pred_kind[1]} !==
               {expected_pc,expected_pred_target,expected_pred_taken,expected_pred_kind})
                $fatal(1,"ALU metadata did not follow the original acceptance/stall edge");
            if({source_pc[0],out_pred_target[0],out_pred_taken[0],out_pred_kind[0]} !== 67'b0)
                $fatal(1,"Disabled ALU metadata is not constant zero");
            checks=checks+1;
        end
    end
    initial begin
        #200000;
        $fatal(1,"ALU metadata test timeout");
    end
    initial begin
        repeat(3) @(negedge clk);
        #1; reset=0;
        // A maximum-length iterative shift retains its original packet while
        // unrelated input metadata changes and the result remains blocked.
        op=`RV32IM_OP_SLL; src1=1; src2=31; tag=16'h15; pc=32'h12345678;
        pred_target=32'h8abcdef0; pred_taken=1; pred_kind=3; issue_valid=1;
        @(negedge clk); #1; issue_valid=0; pc=32'hdeadbeef;
        pred_target=32'h0badcafe; pred_taken=0; pred_kind=1;
        repeat(40) @(negedge clk);
        #1;
        if(!valid[1] || value[1]!==32'h80000000 || source_pc[1]!==32'h12345678)
            $fatal(1,"Shift result/packet not retained through output backpressure");
        // The existing stale-result clear takes priority over a simultaneously
        // offered packet, even though combinational issue_ready is asserted.
        live_valid=1; live_tag=16'h35; tag=16'h35; op=`RV32IM_OP_ADD;
        pc=32'h87654321; pred_target=32'h13579bdf; pred_kind=2; issue_valid=1;
        @(negedge clk); #1;
        if(source_pc[1]!==32'h12345678)
            $fatal(1,"Metadata captured a packet on the stale-result cancellation edge");
        @(negedge clk); #1;
        if(!valid[1] || source_pc[1]!==32'h87654321 || out_pred_target[1]!==32'h13579bdf)
            $fatal(1,"Packet was not captured after the stale result cleared");
        issue_valid=0; flush=1;
        @(negedge clk); #1; flush=0; live_valid=0;
        for(cycle=0;cycle<4000;cycle=cycle+1) begin
            @(negedge clk); #1;
            op=next_random()%64; pc=next_random(); imm=next_random();
            src1=next_random(); src2=next_random(); store_data=next_random();
            pred_target=next_random(); pred_kind=next_random()%4; pred_taken=next_random()%2;
            tag=next_random(); phys=next_random()%64; epoch=next_random()%16;
            mem_size=next_random()%4; mem_unsigned=next_random()%2;
            issue_valid=(next_random()%4)!=0; exec_ready=(next_random()%3)!=0;
            target_live=(next_random()%5)!=0; live_valid=(next_random()%5)==0;
            live_tag=(next_random()%2) ? out_tag[0] : next_random();
            flush=(next_random()%37)==0;
        end
        @(negedge clk); #1;
        if(checks<4000 || accepted<100)
            $fatal(1,"Insufficient ALU metadata coverage");
        $display("PASS: ALU metadata SHIFT_IMPL=%0d checks=%0d accepted=%0d",SHIFT_IMPL,checks,accepted);
        $finish(0);
    end
endmodule
