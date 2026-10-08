`timescale 1ns/1ps
// Narrow generation fixture exercises wrap quickly; production tag widths stay unchanged.
module rv32_single_generation_tb;
reg clk=0,reset=1; always #5 clk=~clk;
reg ra=0,rc=0,la=0,lr=0; reg [7:0] rtag=0,ltag=0;
wire [7:0] rat[0:1],rct[0:1],lat[0:1],lqt[0:1];
wire raf[0:1],rcv[0:1],laf[0:1],lqv[0:1],lcv[0:1];
wire [31:0] rval[0:1],lval[0:1];wire [2:0] rocc[0:1],locc[0:1];
reg [7:0] saved_r[0:3],saved_l[0:3];reg [7:0] current_r,current_l;
integer n,limit;
genvar p;generate for(p=0;p<2;p=p+1) begin:g_policy
rv32_rob #(.SINGLE_GENERATION_OWNER(p),.BE_WIDTH(1),.ROB_ENTRIES(4),.PHYS_ADDR_WIDTH(6),.TAG_WIDTH(8),.GENERATION_WIDTH(3),.PHYS_REGS(64),.CHECKPOINT_WIDTH(32),.LIGHT_RETIRE_PAYLOAD(1),.MMIO_PREDECODE(1),.COMMIT_BANKED_READ(1),.ALLOC_BANKED_WRITE(1),.ROB_CONTROL_REGISTER_BANKS(1)) rob (
.clk_i(clk),
.reset_i(reset),
.alloc_valid_i(ra),
.alloc_pc_i('0),
.alloc_inst_i(32'h13),
.alloc_rd_i('0),
.alloc_rd_we_i('0),
.alloc_old_phys_i('0),
.alloc_new_phys_i('0),
.alloc_is_store_i('0),
.alloc_is_branch_i('0),
.alloc_is_halt_i('0),
.alloc_is_error_i('0),
.alloc_checkpoint_i('0),
.alloc_fire_o(raf[p]),
.alloc_tag_o(rat[p]),
.fast_store_valid_i('0),
.fast_store_tag_i('0),
.completion_valid_i(rc),
.completion_tag_i(rtag),
.completion_value_i(32'h13579bdf),
.completion_done_i(rc),
.completion_error_i('0),
.completion_store_addr_i('0),
.completion_store_mask_i('0),
.completion_store_data_i('0),
.commit_ready_i(1'b1),
.commit_valid_o(rcv[p]),
.commit_value_o(rval[p]),
.commit_tag_o(rct[p]),
.store_commit_ready_i('0),
.store_ack_valid_i('0),
.store_ack_tag_i('0),
.store_ack_error_i('0),
.recovery_valid_i('0),
.recovery_tag_i('0),
.recovery_pc_i('0),
.recovery_apply_i('0),
.recovery_hold_i('0),
.occupancy_o(rocc[p])
);
rv32_lsq #(.SINGLE_GENERATION_OWNER(p),.BE_WIDTH(1),.ROB_ENTRIES(4),.PHYS_ADDR_WIDTH(6),.TAG_WIDTH(8),.GENERATION_WIDTH(3),.LSQ_ENTRIES(4),.ROB_TAG_WIDTH(8),.REQUEST_PIPELINE(1),.EMPTY_SELECTION_BYPASS(2),.PICK_LOCAL_VALIDITY(1)) lsq (
.clk_i(clk),
.reset_i(reset),
.flush_i('0),
.recovery_valid_i('0),
.recovery_tag_i('0),
.recovery_head_i('0),
.recovery_occupancy_i('0),
.retire_valid_i('0),
.retire_rob_tag_i('0),
.alloc_valid_i(la),
.alloc_plan_valid_i(la),
.alloc_fire_o(laf[p]),
.alloc_lsq_tag_o(lat[p]),
.alloc_is_load_i(la),
.alloc_is_store_i('0),
.alloc_rob_tag_i(8'h21),
.alloc_phys_rd_i('0),
.alloc_size_i(2'd2),
.alloc_unsigned_i('0),
.alloc_addr_valid_i(la),
.alloc_addr_i(32'h100),
.alloc_data_valid_i('0),
.alloc_store_data_i('0),
.alloc_store_mask_i('0),
.early_addr_valid_i('0),
.early_addr_tag_i('0),
.early_addr_i('0),
.addr_update_valid_i('0),
.addr_update_tag_i('0),
.addr_update_i('0),
.data_update_valid_i('0),
.data_update_tag_i('0),
.data_update_i('0),
.data_mask_update_i('0),
.wakeup_valid_i('0),
.wakeup_tag_i('0),
.wakeup_value_i('0),
.store_commit_valid_i('0),
.store_commit_rob_tag_i('0),
.dcache_req_valid_o(lqv[p]),
.dcache_req_ready_i(1'b1),
.dcache_req_lsq_tag_o(lqt[p]),
.dcache_resp_valid_i(lr),
.dcache_resp_lsq_tag_i(ltag),
.dcache_resp_query_valid_i('0),
.dcache_resp_query_tags_i('0),
.dcache_resp_addr_i('0),
.dcache_resp_line_data_i('0),
.dcache_resp_word_data_i(32'h2468ace0),
.dcache_resp_line_valid_i('0),
.dcache_resp_error_i('0),
.load_complete_valid_o(lcv[p]),
.load_complete_ready_i(1'b1),
.load_complete_value_o(lval[p]),
.dcache_store_ack_valid_i('0),
.dcache_store_ack_lsq_tag_i('0),
.dcache_store_ack_error_i('0),
.store_ack_query_valid_i('0),
.store_ack_query_tag_i('0),
.store_ack_ready_i(1'b1),
.occupancy_o(locc[p]),
.report_recovery_packet_i('0)
);
end endgenerate
// Compare the public owner-bearing packets, not invalid row generation bits.
always @(negedge clk) if(!reset) begin
 if(raf[0]!==raf[1] || (raf[0] && rat[0]!==rat[1]) || rocc[0]!==rocc[1] ||
    rcv[0]!==rcv[1] || (rcv[0] && {rct[0],rval[0]}!=={rct[1],rval[1]})) $fatal(1,"ROB owner policies differ");
 if(laf[0]!==laf[1] || (laf[0] && lat[0]!==lat[1]) || locc[0]!==locc[1] ||
    lqv[0]!==lqv[1] || (lqv[0] && lqt[0]!==lqt[1]) ||
    lcv[0]!==lcv[1] || (lcv[0] && lval[0]!==lval[1])) $fatal(1,"LSQ owner policies differ");
end
task tick;begin @(posedge clk);#1;end endtask
initial begin
 tick;tick;reset=0;
 for(n=0;n<32;n=n+1) begin
  ra=1;#1;current_r=rat[0];if(!raf[0] || rat[0]!==rat[1] || current_r[7:5]!==((n/4)%7+1)) $fatal(1,"ROB initial/wrap sequence");
  tick;ra=0;
  if(n>=4) begin
   rc=1;rtag=saved_r[n%4];tick;rc=0;
   if(rcv[0] || rcv[1]) $fatal(1,"ROB accepted previous full generation");
  end
  rc=1;rtag=current_r;tick;rc=0;
  if(!rcv[0] || !rcv[1] || rct[0]!==current_r || rval[0]!==32'h13579bdf) $fatal(1,"ROB lost current completion");
  tick;saved_r[n%4]=current_r;
  la=1;#1;current_l=lat[0];if(!laf[0] || lat[0]!==lat[1] || current_l[7:5]!==((n/4)%7+1)) $fatal(1,"LSQ initial/wrap sequence");
  tick;la=0;
  for(limit=0;limit<8 && !lqv[0];limit=limit+1) tick;
  if(!lqv[0] || !lqv[1] || lqt[0]!==current_l) $fatal(1,"LSQ request ownership");
  tick;
  if(n>=4) begin
   lr=1;ltag=saved_l[n%4];tick;lr=0;
   if(lcv[0] || lcv[1]) $fatal(1,"LSQ accepted previous full generation");
  end
  lr=1;ltag=current_l;tick;lr=0;
  if(!lcv[0] || !lcv[1] || lval[0]!==32'h2468ace0) $fatal(1,"LSQ lost current reply");
  for(limit=0;limit<8 && locc[0]!=0;limit=limit+1) tick;
  if(locc[0]!=0 || locc[1]!=0) $fatal(1,"LSQ failed drain");saved_l[n%4]=current_l;
 end
 $display("PASS: limited single generation owner sample");$finish;
end
initial begin #20000;$fatal(1,"single owner sample timeout");end
endmodule
