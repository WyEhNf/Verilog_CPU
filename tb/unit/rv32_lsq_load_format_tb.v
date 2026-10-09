`timescale 1ns/1ps
module rv32_lsq_load_format_tb;
    wire old_done,new_done;
    rv32_lsq_direct_phase_fixture #(.DIRECT_PHASE(1),.DISTRIBUTED_FORMAT(0)) old_impl (.done(old_done));
    rv32_lsq_direct_phase_fixture #(.DIRECT_PHASE(1),.DISTRIBUTED_FORMAT(1)) new_impl (.done(new_done));
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
    reg [31:0] raw=0;
    reg [1:0] size=0;
    reg unsigned_load=0,qualified=0;
    wire [31:0] formatted;
    reg [31:0] expected;
    integer point;
    rv32_frequency_load_format format_sample (
        .raw_i(raw),.size_i(size),.unsigned_i(unsigned_load),.valid_i(qualified),.value_o(formatted));
    // Sixteen points cover four size codes, unsigned/valid both states,
    // negative byte/half signs and a nontrivial complete word. No sweep.
    initial for(point=0;point<16;point=point+1) begin
        size=point[1:0];unsigned_load=point[2];qualified=point[3];
        raw=32'hba988180;
        case(size)
            0: expected=unsigned_load?{24'b0,raw[7:0]}:{{24{raw[7]}},raw[7:0]};
            1: expected=unsigned_load?{16'b0,raw[15:0]}:{{16{raw[15]}},raw[15:0]};
            default: expected=raw;
        endcase
        if(!qualified) expected=0;
        #1;
        if(formatted!==expected) $fatal(1,"bounded formatter point differs from original function");
    end
    initial begin
        wait(old_done && new_done);#4;
        $display("PASS: limited paired LSQ LOAD-format sample");$finish;
    end
endmodule
