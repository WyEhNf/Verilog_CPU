`timescale 1ns/1ps
module rv32_frequency_polarity_tb;
    reg [8:0] source=0;integer vector_id;
    wire [9*4-1:0] old4,new4;
    wire [9*8-1:0] old8,new8;
    wire [9*22-1:0] old22,new22;
    wire [9*64-1:0] old64,new64;
    rv32_frequency_control_tree #(.WIDTH(9),.LEAVES(4),.BALANCED_POLARITY(0)) a (.signal_i(source),.views_o(old4));
    rv32_frequency_control_tree #(.WIDTH(9),.LEAVES(4),.BALANCED_POLARITY(1)) b (.signal_i(source),.views_o(new4));
    rv32_frequency_control_tree #(.WIDTH(9),.LEAVES(8),.BALANCED_POLARITY(0)) c (.signal_i(source),.views_o(old8));
    rv32_frequency_control_tree #(.WIDTH(9),.LEAVES(8),.BALANCED_POLARITY(1)) d (.signal_i(source),.views_o(new8));
    rv32_frequency_control_tree #(.WIDTH(9),.LEAVES(22),.BALANCED_POLARITY(0)) e (.signal_i(source),.views_o(old22));
    rv32_frequency_control_tree #(.WIDTH(9),.LEAVES(22),.BALANCED_POLARITY(1)) f (.signal_i(source),.views_o(new22));
    rv32_frequency_control_tree #(.WIDTH(9),.LEAVES(64),.BALANCED_POLARITY(0)) g (.signal_i(source),.views_o(old64));
    rv32_frequency_control_tree #(.WIDTH(9),.LEAVES(64),.BALANCED_POLARITY(1)) h (.signal_i(source),.views_o(new64));
    initial begin
        for(vector_id=0;vector_id<12;vector_id=vector_id+1) begin
            source=(vector_id==0)?9'b0:(vector_id==1)?9'h1ff:9'(1<<(vector_id-2));#1;
            if(old4!==new4 || new4!=={4{source}} || old8!==new8 || new8!=={8{source}} ||
               old22!==new22 || new22!=={22{source}} || old64!==new64 || new64!=={64{source}})
                $fatal(1,"Balanced control tree changed a positive leaf");
        end
        $display("PASS: limited polarity tree, twelve vectors on four actual RTL tree shapes");$finish;
    end
endmodule
