`timescale 1ns/1ps

module rv32_physical_register_file_tb #(
    parameter integer BE_WIDTH = 1,
    parameter integer PHYS_REGS = 64
);
    localparam integer ADDR_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS);
    reg clk;
    reg reset;
    reg [(2*BE_WIDTH*ADDR_WIDTH)-1:0] read_phys;
    wire [(2*BE_WIDTH*32)-1:0] read_data;
    wire [(2*BE_WIDTH)-1:0] read_ready;
    reg [(BE_WIDTH*ADDR_WIDTH)-1:0] alloc_phys;
    reg [BE_WIDTH-1:0] alloc_valid;
    reg [(BE_WIDTH*ADDR_WIDTH)-1:0] write_phys;
    reg [(BE_WIDTH*32)-1:0] write_data;
    reg [BE_WIDTH-1:0] write_valid;
    integer i;
    integer bad;

    rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS)) dut (
        .clk_i(clk), .reset_i(reset),
        .read_phys_i(read_phys), .read_data_o(read_data), .read_ready_o(read_ready),
        .alloc_phys_i(alloc_phys), .alloc_valid_i(alloc_valid),
        .write_phys_i(write_phys), .write_data_i(write_data), .write_valid_i(write_valid)
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end

    task set_read;
        input integer port;
        input integer phys;
        begin read_phys[(port*ADDR_WIDTH) +: ADDR_WIDTH] = phys[ADDR_WIDTH-1:0]; end
    endtask

    task set_write;
        input integer lane;
        input integer phys;
        input [31:0] data;
        begin
            write_phys[(lane*ADDR_WIDTH) +: ADDR_WIDTH] = phys[ADDR_WIDTH-1:0];
            write_data[(lane*32) +: 32] = data;
            write_valid[lane] = 1'b1;
        end
    endtask

    initial begin
        reset = 1'b1;
        read_phys = {(2*BE_WIDTH*ADDR_WIDTH){1'b0}};
        write_phys = {(BE_WIDTH*ADDR_WIDTH){1'b0}};
        write_data = {(BE_WIDTH*32){1'b0}};
        write_valid = {BE_WIDTH{1'b0}};
        alloc_phys = {(BE_WIDTH*ADDR_WIDTH){1'b0}};
        alloc_valid = {BE_WIDTH{1'b0}};
        bad = 0;
        #12;
        reset = 1'b0;
        #1;
        set_read(0, 0);
        set_read(1, 1);
        #1;
        // Unready PRF data is intentionally unspecified; only its ready bit is
        // part of the contract.  x0 remains the sole reset-readable value.
        if (!read_ready[0] || read_data[31:0] !== 32'b0 || read_ready[1]) begin
            $display("DBG reset fail data=%h ready=%b", read_data, read_ready);
            bad = bad + 1;
        end

        // Same-cycle RAW bypass, including deterministic highest-lane priority.
        set_write(0, 3, 32'h11111111);
        if (BE_WIDTH > 1) set_write(1, 3, 32'h22222222);
        set_read(0, 3);
        #1;
        if (!read_ready[0] || read_data[31:0] !== ((BE_WIDTH > 1) ? 32'h22222222 : 32'h11111111)) begin $display("DBG bypass fail data=%h ready=%b", read_data, read_ready); bad = bad + 1; end
        @(posedge clk); #1;
        write_valid = {BE_WIDTH{1'b0}};
        #1;
        if (!read_ready[0] || read_data[31:0] !== ((BE_WIDTH > 1) ? 32'h22222222 : 32'h11111111)) begin $display("DBG commit fail data=%h ready=%b", read_data, read_ready); bad = bad + 1; end

        // Allocation clears ready on the edge.  A simultaneous CDB write wins.
        alloc_phys[ADDR_WIDTH-1:0] = 3;
        alloc_valid[0] = 1'b1;
        @(posedge clk); #1;
        alloc_valid = {BE_WIDTH{1'b0}};
        if (read_ready[0]) bad = bad + 1;
        alloc_phys[ADDR_WIDTH-1:0] = 3;
        alloc_valid[0] = 1'b1;
        set_write(0, 3, 32'h33333333);
        @(posedge clk); #1;
        alloc_valid = {BE_WIDTH{1'b0}};
        write_valid = {BE_WIDTH{1'b0}};
        if (!read_ready[0] || read_data[31:0] !== 32'h33333333) bad = bad + 1;

        // x0 remains zero/ready and cannot be overwritten.
        set_write(0, 0, 32'hdeadbeef);
        set_read(0, 0);
        #1;
        if (!read_ready[0] || read_data[31:0] !== 32'b0) begin $display("DBG x0 bypass fail data=%h ready=%b", read_data, read_ready); bad = bad + 1; end
        @(posedge clk); #1;
        write_valid = {BE_WIDTH{1'b0}};
        #1;
        if (!read_ready[0] || read_data[31:0] !== 32'b0) begin $display("DBG x0 commit fail data=%h ready=%b", read_data, read_ready); bad = bad + 1; end

        // Non-power-of-two configurations reject encoded addresses above the array.
        if ((1 << ADDR_WIDTH) > PHYS_REGS) begin
            set_read(0, PHYS_REGS + 1);
            #1;
            if (read_ready[0] || read_data[31:0] !== 32'b0) begin $display("DBG invalid bypass fail data=%h ready=%b", read_data, read_ready); bad = bad + 1; end
            set_write(0, PHYS_REGS + 1, 32'hcafebabe);
            @(posedge clk); #1;
            write_valid = {BE_WIDTH{1'b0}};
            set_read(0, PHYS_REGS + 1);
            #1;
            if (read_ready[0] || read_data[31:0] !== 32'b0) begin $display("DBG invalid commit fail data=%h ready=%b", read_data, read_ready); bad = bad + 1; end
        end

        if (bad != 0) begin
            $display("FAIL: B-01 PRF BE_WIDTH=%0d PHYS_REGS=%0d checks=%0d", BE_WIDTH, PHYS_REGS, bad);
            $finish(1);
        end
        $display("PASS: B-01 PRF BE_WIDTH=%0d PHYS_REGS=%0d", BE_WIDTH, PHYS_REGS);
        $finish(0);
    end
endmodule
