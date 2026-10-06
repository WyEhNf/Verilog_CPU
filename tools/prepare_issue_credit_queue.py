"""Freeze a two-slot issue boundary; no functional test is run here."""
from pathlib import Path
import hashlib, json, shutil

BASE = Path('F:/CPU2026Candidates/control_islands_v2_20261003')
STAGE = Path('F:/CPU2026Candidates/issue_credit_queue_v3_20261003')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

SLOT = r'''
// Two entries preserve one-cycle forward latency and one acceptance per cycle.
// The upstream credit comes exclusively from registered occupancy. A stalled
// completion source cannot propagate combinational ready through this boundary.
(* keep_hierarchy = 1 *)
module rv32_issue_pipeline_slot #(
    parameter integer PAYLOAD_WIDTH=192, TAG_WIDTH=17, ROB_ENTRIES=64,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES)
) (
    input wire clk_i, reset_i, flush_i, recovery_i,
    input wire [SW-1:0] head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire valid_i, eligible_i,
    output wire ready_o,
    input wire [PAYLOAD_WIDTH-1:0] data_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire valid_o,
    input wire ready_i,
    output wire [PAYLOAD_WIDTH-1:0] data_o
);
    reg [1:0] count;
    reg read_row, write_row;
    reg [TAG_WIDTH-1:0] tag0, tag1;
    wire [SW-1:0] branch_age = recovery_tag_i[3 +: SW] - head_i;
    wire [SW-1:0] age0 = tag0[3 +: SW] - head_i;
    wire [SW-1:0] age1 = tag1[3 +: SW] - head_i;
    wire present0 = count==2 || (count==1 && !read_row);
    wire present1 = count==2 || (count==1 && read_row);
    wire retain0 = present0 && age0<branch_age;
    wire retain1 = present1 && age1<branch_age;
    assign valid_o = count!=0 && !reset_i && !flush_i && !recovery_i;
    assign ready_o = count!=2 && eligible_i && !reset_i && !flush_i && !recovery_i;
    wire push = ready_o && valid_i;
    wire pop = valid_o && ready_i;
    wire write0 = push && !write_row;
    wire write1 = push && write_row;

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            count<=0; read_row<=0; write_row<=0;
            tag0<=0; tag1<=0;
        end else if (recovery_i) begin
            // RS selection is out of order: either physical row may survive.
            // Compact by moving the read pointer, without copying wide data.
            case ({retain1,retain0})
                2'b00: begin count<=0; read_row<=0; write_row<=0; end
                2'b01: begin count<=1; read_row<=0; write_row<=1; end
                2'b10: begin count<=1; read_row<=1; write_row<=0; end
                2'b11: begin count<=2; end
            endcase
        end else begin
            case ({push,pop})
                2'b10: count<=count+1'b1;
                2'b01: count<=count-1'b1;
                default: count<=count;
            endcase
            if (pop) read_row<=!read_row;
            if (push) write_row<=!write_row;
            if (write0) tag0<=tag_i;
            if (write1) tag1<=tag_i;
        end
    end
    // These banks own the actual payload state and its hold/read muxes.
    // Each shared write decision drives one port per 32-bit field.
    genvar field;
    generate for (field=0;field<(PAYLOAD_WIDTH+31)/32;field=field+1) begin:g_field
        localparam integer WIDTH=(PAYLOAD_WIDTH-field*32<32)?PAYLOAD_WIDTH-field*32:32;
        rv32_issue_queue_field #(.WIDTH(WIDTH)) bank (
            .clk_i(clk_i),.write0_i(write0),.write1_i(write1),
            .read_row_i(read_row),.data_i(data_i[field*32 +: WIDTH]),
            .data_o(data_o[field*32 +: WIDTH]));
    end endgenerate
endmodule

(* keep_hierarchy = 1 *)
module rv32_issue_queue_field #(parameter integer WIDTH=32) (
    input wire clk_i,write0_i,write1_i,read_row_i,
    input wire [WIDTH-1:0] data_i,
    output wire [WIDTH-1:0] data_o
);
    reg [WIDTH-1:0] row0,row1;
    always @(posedge clk_i) begin
        if (write0_i) row0<=data_i;
        if (write1_i) row1<=data_i;
    end
    assign data_o=read_row_i?row1:row0;
endmodule
'''

def main():
    assert not STAGE.exists(), 'Preserve previous frozen candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for name,h in manifest['source_sha256'].items():
        assert sha(BASE/name)==h.lower(),name
        dest=STAGE/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(BASE/name,dest)
    dest=STAGE/'rtl/backend/rv32_backend_joint.v'
    text=dest.read_text(encoding='utf-8')
    start=text.index('// A selected instruction is removed from the RS only when this slot accepts it.')
    assert text[start:].count('module ')==1
    dest.write_text(text[:start]+SLOT,encoding='utf-8')
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},
        strategy=manifest['strategy']+'; two-slot registered-credit issue queues with recovery compaction and local payload fields',
        tool_sha256=sha(__file__))
    manifest['changed']=manifest['changed']+[dict(file='rtl/backend/rv32_backend_joint.v',
        change='Replace one-slot fall-through-ready issue boundary with two-slot registered credits')]
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True)))

if __name__=='__main__':main()
