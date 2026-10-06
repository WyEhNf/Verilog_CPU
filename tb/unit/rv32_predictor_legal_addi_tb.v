`timescale 1ns/1ps
module rv32_predictor_legal_addi_tb;
    parameter integer WIDTH=4, LEGACY=0;
    reg clk=0, reset=1;
    always #5 clk=~clk;
    wire [WIDTH*16-1:0] metadata;
    integer lane;
    rv32_banked_predictor #(.FE_WIDTH(WIDTH), .DIRECT_BRANCH_TARGET(2),
        .LEGACY_SENTINEL_HALT(LEGACY)) dut (
        .clk_i(clk), .reset_i(reset), .query_valid_i(1'b1),
        .query_pc_i(32'd0), .query_line_i(128'h0000000000000000000000000ff00513),
        .query_accept_i(1'b0), .effective_pred_taken_i({WIDTH{1'b0}}),
        .recovery_valid_i(1'b0), .recovery_history_i(8'd0),
        .pred_metadata_o(metadata), .pred_taken_o(), .pred_btb_hit_o(),
        .pred_target_o(), .pred_kind_o(), .pred_counter_o(),
        .pred_bht_index_o(), .pred_btb_index_o(),
        .feedback_valid_i(1'b0), .feedback_pc_i(32'd0), .feedback_kind_i(2'd0),
        .feedback_taken_i(1'b0), .feedback_target_i(32'd0),
        .feedback_pred_taken_i(1'b0), .feedback_pred_target_i(32'd0),
        .feedback_metadata_i(16'd0), .prediction_count_o(), .correct_count_o()
    );
    initial begin
        repeat(2) @(negedge clk);
        reset=0; #1;
        for(lane=0; lane<WIDTH; lane=lane+1) begin
            if(metadata[lane*16 +: 16] !== ((LEGACY!=0) ? 16'd0 : lane[15:0]))
                $fatal(1,"Legal ADDI255 truncated predictor prefix lane=%0d",lane);
        end
        $display("PASS: predictor ADDI255 WIDTH=%0d LEGACY=%0d",WIDTH,LEGACY);
        $finish;
    end
    initial begin #5000; $fatal(1,"Predictor ADDI255 test timeout"); end
endmodule
