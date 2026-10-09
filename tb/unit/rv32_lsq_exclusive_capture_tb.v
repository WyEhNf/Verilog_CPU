`timescale 1ns/1ps
module rv32_lsq_exclusive_capture_tb;
    wire old_done,new_done;
    rv32_lsq_direct_phase_fixture #(.DIRECT_PHASE(1),.DISTRIBUTED_FORMAT(1),.EXCLUSIVE_ALLOC(0),.RELEASE_POLICY(0),.PLANNED_ALLOC(1)) old_impl (.done(old_done));
    rv32_lsq_direct_phase_fixture #(.DIRECT_PHASE(1),.DISTRIBUTED_FORMAT(1),.EXCLUSIVE_ALLOC(1),.RELEASE_POLICY(0),.PLANNED_ALLOC(1)) new_impl (.done(new_done));
    // Compare observable public handshakes and their owned payloads. Unowned
    // stale words are not required to agree across the two storage policies.
    always @(negedge old_impl.clk) begin
        #3;
        if(!old_impl.reset && !new_impl.reset) begin
            if({old_impl.alloc_ready,old_impl.commit_ready,old_impl.request_valid,old_impl.store_ack_valid,old_impl.load_valid,old_impl.occupancy} !==
               {new_impl.alloc_ready,new_impl.commit_ready,new_impl.request_valid,new_impl.store_ack_valid,new_impl.load_valid,new_impl.occupancy})
                $fatal(1,"saved-query LSQ public handshake/cycle mismatch");
            if(old_impl.routed_mmio !== new_impl.routed_mmio ||
               new_impl.routed_mmio !== new_impl.original_mmio_class)
                $fatal(1,"saved MMIO routing differs from original qualified predicate");
            if(old_impl.request_valid &&
               {old_impl.request_store,old_impl.request_addr,old_impl.request_tag,old_impl.request_mask,old_impl.request_data} !==
               {new_impl.request_store,new_impl.request_addr,new_impl.request_tag,new_impl.request_mask,new_impl.request_data})
                $fatal(1,"saved-query LSQ owned request payload mismatch");
            if(old_impl.load_valid &&
               {old_impl.load_value,old_impl.load_rob_tag,old_impl.selected_phys,old_impl.load_error} !==
               {new_impl.load_value,new_impl.load_rob_tag,new_impl.selected_phys,new_impl.load_error})
                $fatal(1,"saved-query LSQ owned completion payload mismatch");
        end
    end
    initial begin
        wait(old_done && new_done);#4;
        $display("PASS: limited paired LSQ exclusive-capture sample");$finish;
    end
endmodule
