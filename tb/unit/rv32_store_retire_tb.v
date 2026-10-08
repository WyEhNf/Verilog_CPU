`timescale 1ns/1ps
module rv32_store_retire_tb;
reg clk=0,reset=1;always #5 clk=~clk;
reg [1:0] av=0,ab=0,ah=0,ast=0,cv=0,ce=0;
reg [15:0] ct=0;reg [63:0] val=0;reg ready=1,hold=0,store_ready=0,ack=0;reg [31:0] addr=0,sdata=0;reg [3:0] mask=0;reg [7:0] ack_tag=0;
wire [1:0] af,rv;wire [15:0] at,rt;wire [63:0] rval;
wire [2:0] occ;wire halted,error,store_valid;wire [7:0] store_tag;
reg [7:0] old0,young1,ticket;integer n;
rv32_rob #(.STORE_RETIRE_ADMISSION_BYPASS(1),.STAGED_RECOVERY(1),.COMPLETION_COMMIT_BYPASS(1),.SINGLE_GENERATION_OWNER(1),.BE_WIDTH(2),.ROB_ENTRIES(4),.PHYS_REGS(64),.PHYS_ADDR_WIDTH(6),.GENERATION_WIDTH(3),.TAG_WIDTH(8),.CHECKPOINT_WIDTH(32),.LIGHT_RETIRE_PAYLOAD(1),.MMIO_PREDECODE(1),.COMMIT_BANKED_READ(1),.ALLOC_BANKED_WRITE(1),.ROB_CONTROL_REGISTER_BANKS(1)) dut (
.clk_i(clk),
.reset_i(reset),
.alloc_valid_i(av),
.alloc_pc_i('0),
.alloc_inst_i('0),
.alloc_rd_i('0),
.alloc_rd_we_i('0),
.alloc_old_phys_i('0),
.alloc_new_phys_i('0),
.alloc_is_store_i(ast),
.alloc_is_branch_i(ab),
.alloc_is_halt_i(ah),
.alloc_is_error_i('0),
.alloc_checkpoint_i('0),
.alloc_fire_o(af),
.alloc_tag_o(at),
.fast_store_valid_i('0),
.fast_store_tag_i('0),
.completion_valid_i(cv),
.completion_tag_i(ct),
.completion_value_i(val),
.completion_done_i(cv),
.completion_error_i(ce),
.completion_store_addr_i({32'b0,addr}),
.completion_store_mask_i({4'b0,mask}),
.completion_store_data_i({32'b0,sdata}),
.commit_ready_i(ready),
.commit_valid_o(rv),
.commit_value_o(rval),
.commit_tag_o(rt),
.store_commit_valid_o(store_valid),.store_commit_tag_o(store_tag),
.store_commit_ready_i(store_ready),
.store_ack_valid_i(ack),
.store_ack_tag_i(ack_tag),
.store_ack_error_i('0),
.recovery_valid_i('0),
.recovery_tag_i('0),
.recovery_pc_i('0),
.recovery_apply_i('0),
.recovery_hold_i(hold),
.halted_o(halted),
.error_o(error),
.occupancy_o(occ));
task tick;begin @(posedge clk);#1;end endtask
task clear;begin av=0;ab=0;ah=0;ast=0;cv=0;ce=0;end endtask
task alloc_one;begin av=1;#1;if(af!=1) $fatal(1,"allocation failed");ticket=at[7:0];tick;av=0;end endtask
task complete_ordinary;begin cv=1;ct={8'b0,ticket};val=64'h13579bdf;#1;
 if(rv!=1 || rt[7:0]!=ticket || rval[31:0]!=32'h13579bdf) $fatal(1,"ordinary same-edge commit missing");tick;cv=0;
 if(occ!=0) $fatal(1,"ordinary same-edge commit failed pop");end endtask
initial begin
 tick;tick;reset=0;av=3;#1;old0=at[7:0];young1=at[15:8];tick;av=0;
 cv=1;ct={8'b0,young1};val=64'd22;#1;if(rv!=0) $fatal(1,"younger completion crossed unresolved head");tick;cv=0;
 ready=0;cv=1;ct={8'b0,old0};val=64'd11;#1;
 if(rv!=3 || rval!={32'd22,32'd11} || rt!={young1,old0}) $fatal(1,"mixed stored/fresh ordered commit prefix");
 tick;cv=0;#1;if(rv!=3 || rval!={32'd22,32'd11} || occ!=2) $fatal(1,"held commit changed after completion edge");
 ready=1;tick;if(occ!=0) $fatal(1,"held prefix failed retire");
 for(n=0;n<2;n=n+1) begin alloc_one;complete_ordinary;end
 alloc_one;cv=1;ct={8'b0,old0};val=64'hffffffff;#1;if(rv!=0) $fatal(1,"stale full generation bypassed");tick;cv=0;complete_ordinary;
 ab=1;alloc_one;ab=0;cv=1;ct={8'b0,ticket};#1;if(rv!=0) $fatal(1,"branch bypassed ready state");tick;cv=0;#1;if(rv!=1) $fatal(1,"registered branch lost");tick;
 alloc_one;hold=1;cv=1;ct={8'b0,ticket};#1;if(rv!=0) $fatal(1,"recovery hold leaked commit");tick;cv=0;#1;if(rv!=0) $fatal(1,"held recovery leaked saved commit");hold=0;tick;
 ast=1;alloc_one;ast=0;cv=1;ct={8'b0,ticket};#1;if(rv!=0 || store_valid) $fatal(1,"store bypassed admission");tick;cv=0;#1;if(rv!=0 || !store_valid) $fatal(1,"saved store admission changed");store_ready=1;#1;if(rv!=1 || !store_valid || store_tag!=ticket) $fatal(1,"exact head admission did not retire same edge");tick;store_ready=0;#1;if(occ!=0) $fatal(1,"head admission did not pop");
 ast=1;alloc_one;ast=0;addr=32'h80000000;mask=4'hf;sdata=32'h12345678;cv=1;ct={8'b0,ticket};tick;cv=0;#1;
 if(rv!=0 || !store_valid) $fatal(1,"MMIO failed saved admission path");store_ready=1;#1;if(rv!=0) $fatal(1,"MMIO retired on admission before ACK");tick;store_ready=0;
 ack=1;ack_tag=ticket;tick;ack=0;#1;if(rv!=1) $fatal(1,"MMIO lost precise ACK");tick;if(!halted) $fatal(1,"MMIO did not halt after ACK");
 reset=1;clear;addr=0;mask=0;sdata=0;tick;reset=0;
 ah=1;alloc_one;ah=0;cv=1;ct={8'b0,ticket};#1;if(rv!=0 || halted) $fatal(1,"HALT bypassed registered state");tick;cv=0;tick;if(!halted) $fatal(1,"registered HALT lost");reset=1;clear;tick;reset=0;
 alloc_one;cv=1;ce=1;ct={8'b0,ticket};#1;if(rv!=0 || error) $fatal(1,"error bypassed registered state");tick;clear;tick;if(!error) $fatal(1,"precise error lost");
 $display("PASS: limited ROB store retirement sample");$finish;
end
initial begin #2000;$fatal(1,"completion commit sample timeout");end
endmodule
