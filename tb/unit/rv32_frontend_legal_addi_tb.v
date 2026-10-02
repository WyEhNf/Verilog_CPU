`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_frontend_legal_addi_tb;
    parameter integer WIDTH=4, META=0, LEGACY=0;
    localparam integer PW=`RV32IM_FETCH_PACKET_WIDTH;
    reg clk=0, reset=1, redirect=0, response_valid=0;
    always #5 clk=~clk;
    reg [31:0] response_pc=12;
    wire request_valid, response_ready, frozen;
    wire [31:0] request_pc;
    wire [WIDTH-1:0] valid;
    wire [WIDTH*PW-1:0] packet;
    wire [3:0] epoch;
    rv32_fetch_frontend #(.FE_WIDTH(WIDTH),.FQ_DEPTH(8),.PREDICTOR_META(META),
        .LEGACY_SENTINEL_HALT(LEGACY)) dut (
        .clk_i(clk),.reset_i(reset),.redirect_valid_i(redirect),
        .redirect_pc_i(32'd12),.redirect_epoch_i(4'd1),.stop_i(1'b0),.error_i(1'b0),
        .if_req_valid_o(request_valid),.if_req_ready_i(1'b1),.if_req_pc_o(request_pc),.if_req_epoch_o(),
        .if_resp_valid_i(response_valid),.if_resp_ready_o(response_ready),.if_resp_pc_i(response_pc),
        .if_resp_line_addr_i(32'd0),.if_resp_line_data_i(128'h0ff00513000000130000001300000013),
        .if_resp_epoch_i(4'd1),.if_resp_error_i(1'b0),.if_resp_pred_taken_i({WIDTH{1'b0}}),
        .if_resp_pred_target_i({WIDTH*32{1'b0}}),.if_resp_pred_kind_i({WIDTH*2{1'b0}}),
        .if_resp_pred_btb_hit_i({WIDTH{1'b0}}),.if_resp_pred_metadata_i({WIDTH*16{1'b0}}),
        .fetch_pred_metadata_o(),.fetch_valid_o(valid),.fetch_ready_i({WIDTH{1'b0}}),
        .fetch_packet_o(packet),.current_epoch_o(epoch),.frozen_o(frozen),
        .event_fetch_o(),.event_redirect_o(),.event_stall_o()
    );
    initial begin
        repeat(3) @(negedge clk);
        reset=0;redirect=1;
        @(negedge clk);redirect=0;
        @(negedge clk);response_valid=1;
        #1;if(!response_ready) $fatal(1,"Legal response not accepted");
        if(LEGACY==0 && (!request_valid || request_pc!==32'd16))
            $fatal(1,"Ordinary ADDI255 must allow chained next-line fetch");
        @(negedge clk);response_valid=0;#1;
        if(valid!=={{(WIDTH-1){1'b0}},1'b1} || packet[31:0]!==32'd12 || packet[63:32]!==32'h0ff00513)
            $fatal(1,"ADDI255 instruction packet lost or changed");
        if(frozen!==(LEGACY!=0)) $fatal(1,"Legacy halt leaked into ordinary RV32I mode");
        if(request_pc!==32'd16) $fatal(1,"Next sequential PC changed");
        repeat(3) begin
            @(negedge clk);#1;
            if(frozen!==(LEGACY!=0)) $fatal(1,"Frozen state drift under backpressure");
        end
        redirect=1;
        @(negedge clk);redirect=0;#1;
        if(frozen || !request_valid || request_pc!==32'd12) $fatal(1,"Redirect did not restart fetch");
        $display("PASS: legal ADDI255 WIDTH=%0d META=%0d LEGACY=%0d",WIDTH,META,LEGACY);
        $finish;
    end
    initial begin #5000; $fatal(1,"ADDI255 frontend test timeout"); end
endmodule
