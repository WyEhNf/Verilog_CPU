`timescale 1ns/1ps
// Small ordered-stream scoreboard: expected packets come only from public
// input handshakes. It does not mirror queue pointers or internal state.
module rv32_decode_bypass_case #(parameter integer LANES=1) (
    input wire clk,
    output reg done=0
);
    reg reset=0,flush=0;
    reg [LANES-1:0] input_valid=0,output_ready=0;
    wire [LANES-1:0] input_ready,output_valid;
    reg [32*LANES-1:0] input_data=0;
    wire [32*LANES-1:0] output_data;
    integer expected[$];
    integer next_id=1,step=-1,pushed=0,popped=0,before_size;
    integer lane,discard;
    rv32_decode_bundle_register #(.LANES(LANES),.PAYLOAD_WIDTH(32),.CAPACITY(LANES),
        .EMPTY_BYPASS(1),.FULL_REPLACE(1)) dut (
        .clk_i(clk),.reset_i(reset),.flush_i(flush),
        .valid_i(input_valid),.ready_o(input_ready),.data_i(input_data),
        .valid_o(output_valid),.ready_i(output_ready),.data_o(output_data));
    always @(posedge clk) begin
        if(reset || flush) begin
            expected.delete();
            if(input_ready!==0 || output_valid!==0) $fatal(1,"flush accepted/emitted packets reset=%b flush=%b ready=%b valid=%b domains=%b",reset,flush,input_ready,output_valid,dut.invalidate_domains);
        end else begin
            before_size=expected.size();
            if(before_size==0 && input_valid[0] &&
               (!output_valid[0] || output_data[31:0]!==input_data[31:0]))
                $fatal(1,"empty packet did not bypass lanes=%0d step=%0d",LANES,step);
            if(before_size==LANES && output_ready[0] && !input_ready[0])
                $fatal(1,"full queue did not replace lanes=%0d step=%0d",LANES,step);
            for(integer push_lane=0;push_lane<LANES;push_lane=push_lane+1)
                if(input_valid[push_lane] && input_ready[push_lane]) begin
                    expected.push_back(input_data[push_lane*32 +: 32]);
                    pushed=pushed+1;
                    next_id=next_id+1;
                end
            for(integer check_lane=0;check_lane<LANES;check_lane=check_lane+1)
                if(output_valid[check_lane]) begin
                    if(check_lane>=expected.size() ||
                       output_data[check_lane*32 +: 32]!==32'(expected[check_lane]))
                        $fatal(1,"packet order/held payload lanes=%0d step=%0d lane=%0d",LANES,step,check_lane);
                end
            for(integer pop_lane=0;pop_lane<LANES;pop_lane=pop_lane+1)
                if(output_valid[pop_lane] && output_ready[pop_lane]) begin
                    discard=expected.pop_front();
                    popped=popped+1;
                end
            if(expected.size()>LANES) $fatal(1,"queue overflow");
            if(step==17) begin
                if(expected.size()!=0) $fatal(1,"queue did not drain");
                $display("PASS: decode stream lanes=%0d pushes=%0d pops=%0d, bypass/hold/partial/full-replace/flush/drain",LANES,pushed,popped);
                done<=1;
            end
        end
    end
    initial begin
        #1; reset=1;
        repeat(2) @(negedge clk); reset=0;
        for(integer cycle=0;cycle<18;cycle=cycle+1) begin
            step=cycle;
            input_valid=(cycle<12 || cycle==14 || cycle==15 || cycle==16)?{LANES{1'b1}}:0;
            output_ready={LANES{1'b1}};
            if(cycle==1 || cycle==2 || cycle==5 || cycle==6 || cycle==9 || cycle==10)
                output_ready=0;
            if(cycle==3 || cycle==7 || cycle==14) output_ready={{(LANES-1){1'b0}},1'b1};
            flush=cycle==15;
            for(integer source_lane=0;source_lane<LANES;source_lane=source_lane+1)
                input_data[source_lane*32 +: 32]=32'(next_id+source_lane);
            @(negedge clk);
        end
    end
endmodule

module rv32_decode_bypass_tb;
    reg clk=0;
    always #5 clk=~clk;
    wire [2:0] done;
    rv32_decode_bypass_case #(.LANES(1)) one (.clk(clk),.done(done[0]));
    rv32_decode_bypass_case #(.LANES(2)) two (.clk(clk),.done(done[1]));
    rv32_decode_bypass_case #(.LANES(4)) four (.clk(clk),.done(done[2]));
    initial begin wait(&done); $display("PASS: limited shared decode queue sample for 1/2/4 lanes"); $finish; end
    initial begin #5000; $fatal(1,"decode sample timeout"); end
endmodule
