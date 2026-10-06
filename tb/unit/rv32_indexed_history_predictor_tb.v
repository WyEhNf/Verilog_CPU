`timescale 1ns/1ps
`include "rv32im_defs.vh"
module rv32_indexed_history_predictor_tb #(
    parameter integer WIDTH=4,
    parameter integer HISTORY_BITS=6
);
    localparam integer BANK_BITS=$clog2(WIDTH);
    localparam [7:0] HM=(1 << HISTORY_BITS)-1;
    reg clk=0;
    always #5 clk=!clk;
    reg reset=1, qvalid=0, accept=0, recover=0, ras_override=0;
    reg [7:0] recovery_history=0;
    reg [31:0] pc=32'h100;
    reg [127:0] line={4{32'h00208463}};
    reg fvalid=0, ftaken=0;
    reg [31:0] fpc=32'h100;
    reg [1:0] fkind=`RV32IM_PRED_BRANCH;
    reg [15:0] fmetadata=0;
    wire [WIDTH-1:0] taken, effective_taken;
    assign effective_taken=ras_override ? {{(WIDTH-1){1'b0}},1'b1} : taken;
    wire [WIDTH*16-1:0] metadata;
    wire [WIDTH*32-1:0] target;
    reg [15:0] saved;
    reg [7:0] before_history, expected_index;
    integer lane;
    integer step, word_slot, row, seed=32'h591bd874;
    reg [31:0] random_word, query_pc;
    reg [7:0] model_history, next_history, checkpoint;
    reg [1:0] model_counter [0:255];
    reg model_trained [0:255];
    reg prefix_live, expected_taken;
    reg [31:0] expected_target, query_inst;
    rv32_banked_predictor #(.FE_WIDTH(WIDTH), .DIRECT_BRANCH_TARGET(2), .HISTORY_BITS(HISTORY_BITS)) dut (
        .clk_i(clk), .reset_i(reset), .query_valid_i(qvalid), .query_pc_i(pc), .query_line_i(line),
        .query_accept_i(accept), .effective_pred_taken_i(effective_taken),
        .recovery_valid_i(recover), .recovery_history_i(recovery_history), .pred_metadata_o(metadata),
        .pred_taken_o(taken), .pred_target_o(target), .pred_btb_hit_o(), .pred_kind_o(),
        .pred_counter_o(), .pred_bht_index_o(), .pred_btb_index_o(),
        .feedback_valid_i(fvalid), .feedback_pc_i(fpc), .feedback_kind_i(fkind),
        .feedback_taken_i(ftaken), .feedback_target_i(32'h108), .feedback_pred_taken_i(1'b0),
        .feedback_pred_target_i(32'h104), .feedback_metadata_i(fmetadata),
        .prediction_count_o(), .correct_count_o()
    );
    task restore;
        input [7:0] history;
        begin
            @(negedge clk); recover=1; recovery_history=history;
            @(negedge clk); recover=0; #1;
            if (dut.global_history !== (history & HM)) $fatal(1,"Restore did not win");
        end
    endtask
    initial begin
        repeat(2) @(negedge clk); reset=0; qvalid=1;
        restore(8'd3);
        if (taken !== 0) $fatal(1,"Cold forward BTFNT changed");
        before_history=3 & HM;
        for(lane=0;lane<WIDTH;lane=lane+1) begin
            expected_index=(pc+lane*4)>>2;
            expected_index=expected_index ^ ((3 & HM)<<BANK_BITS);
            if (metadata[lane*16 +: 16] !== {before_history, expected_index})
                $fatal(1,"Index/checkpoint mismatched bank/lane");
            before_history=(before_history << 1)&HM;
        end
        saved=metadata[15:0];
        // While held (not accepted), neither speculative history nor its
        // checkpoint changes. Table training is a separate accepted event.
        repeat(3) begin @(negedge clk); if(dut.global_history !== (3&HM)) $fatal(1,"Unaccepted query advanced history"); end
        restore(8'd42);
        @(negedge clk); fvalid=1; ftaken=1; fmetadata=saved;
        @(negedge clk); fvalid=0; #1;
        if(taken !== 0) $fatal(1,"Training incorrectly used current history");
        restore(8'd3);
        if(taken[0] !== 1 || target[31:0] !== 32'h108) $fatal(1,"Saved query index was not trained");
        for(lane=1;lane<WIDTH;lane=lane+1)
            if(metadata[lane*16 +: 16] !== 0) $fatal(1,"Predicted-taken prefix leaked younger checkpoints");
        @(negedge clk); accept=1;
        @(negedge clk); accept=0; #1;
        if(dut.global_history !== (((3&HM)<<1 | 1)&HM)) $fatal(1,"Accepted conditional history update");
        // A return supplied by the core RAS truncates an otherwise raw
        // not-taken JALR. Younger conditional instructions must not advance.
        restore(8'd3);
        line={32'h00208463,32'h00208463,32'h00208463,32'h000080e7};
        ras_override=1; #1;
        @(negedge clk); accept=1;
        @(negedge clk); accept=0; #1;
        if(dut.global_history !== (3&HM)) $fatal(1,"RAS effective prefix not honored");
        ras_override=0; line={4{32'h00208463}};
        @(negedge clk); accept=1; recover=1; recovery_history=5;
        @(negedge clk); accept=0; recover=0; #1;
        if(dut.global_history !== (5&HM)) $fatal(1,"Recovery/query priority wrong");
        pc=32'hfffffffc; #1;
        for(lane=1;lane<WIDTH;lane=lane+1)
            if(metadata[lane*16 +: 16] !== 0) $fatal(1,"Line-tail invalid lane checkpoint leaked");
        @(negedge clk); reset=1;
        @(negedge clk); reset=0; pc=32'h100; #1;
        if(dut.global_history !== 0 || taken !== 0) $fatal(1,"Warm reset left trained/history state");
        model_history=0;
        for(row=0;row<256;row=row+1) begin model_counter[row]=2'b10; model_trained[row]=0; end
        for(step=0;step<1200;step=step+1) begin
            @(negedge clk);
            random_word=$random(seed);
            reset=(step%137)==0;
            qvalid=random_word[0]; accept=qvalid && random_word[1];
            recover=random_word[2]; recovery_history=random_word[15:8];
            fvalid=random_word[3]; ftaken=random_word[4]; ras_override=0;
            fpc=32'h1000+($random(seed)&32'h7fc);
            expected_index=fpc>>2;
            // Represents an independently delayed prediction: this saved
            // history is intentionally unrelated to the CURRENT history.
            expected_index=expected_index ^ ((($random(seed)&HM))<<BANK_BITS);
            fmetadata={8'h79,expected_index};
            pc=32'h1000+($random(seed)&32'h7fc);
            if(step%97==0) pc=32'hfffffffc;
            for(word_slot=0;word_slot<4;word_slot=word_slot+1) begin
                random_word=$random(seed);
                line[word_slot*32 +: 32]=random_word[0] ? 32'hfe208ee3 : 32'h00208463;
            end
            #1;
            if(dut.global_history !== model_history) $fatal(1,"History diverged from independent model");
            checkpoint=model_history; prefix_live=qvalid;
            for(lane=0;lane<WIDTH;lane=lane+1) begin
                query_pc=pc+lane*32'd4;
                expected_index=(query_pc>>2) ^ (model_history<<BANK_BITS);
                query_inst=line>>((pc[3:2]+lane)*32);
                expected_taken=0; expected_target=query_pc+32'd4;
                if(qvalid && (pc[3:2]+lane)<4) begin
                    expected_taken=model_trained[expected_index] ? model_counter[expected_index][1] : query_inst[31];
                    if(expected_taken) expected_target=query_pc+(query_inst[31] ? -32'd4 : 32'd8);
                end
                if(taken[lane] !== expected_taken || target[lane*32 +: 32] !== expected_target)
                    $fatal(1,"Random query/counter model mismatch step=%0d lane=%0d",step,lane);
                if(prefix_live && (pc[3:2]+lane)<4) begin
                    if(metadata[lane*16 +: 16] !== {checkpoint,expected_index})
                        $fatal(1,"Random index/checkpoint model mismatch");
                    checkpoint=((checkpoint<<1)|expected_taken)&HM;
                    if(expected_taken) prefix_live=0;
                end else if(metadata[lane*16 +: 16] !== 0)
                    $fatal(1,"Random invalid prefix metadata leaked");
            end
            next_history=recover ? (recovery_history&HM) : (accept ? checkpoint : model_history);
            @(posedge clk); #1;
            if(reset) begin
                model_history=0;
                for(row=0;row<256;row=row+1) begin model_counter[row]=2'b10; model_trained[row]=0; end
            end else begin
                model_history=next_history;
                if(fvalid) begin
                    row=fmetadata[7:0]; model_trained[row]=1;
                    if(ftaken && model_counter[row]!=3) model_counter[row]=model_counter[row]+1;
                    if(!ftaken && model_counter[row]!=0) model_counter[row]=model_counter[row]-1;
                end
            end
            if(dut.global_history !== model_history) $fatal(1,"Random sequential history update mismatch");
        end
        $display("PASS: indexed history width=%0d bits=%0d saved-index/prefix/RAS/restore/reset",WIDTH,HISTORY_BITS);
        $finish;
    end
    initial begin #30000; $fatal(1,"Indexed predictor timeout"); end
endmodule
