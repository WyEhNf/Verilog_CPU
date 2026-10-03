"""Give AXI response words their own FIFO state at the existing clock boundary."""
from pathlib import Path
import hashlib,json,shutil

BASE=Path('F:/CPU2026Candidates/aligned_fetch_v5_20261003')
STAGE=Path('F:/CPU2026Candidates/response_fields_v6_20261003')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

FIELD=r'''
// Actual response payload storage, with local read/write pointers. All fields
// receive the same accepted transaction pulses, so their rows stay aligned.
// Keeping pointers beside their words bounds each pointer's data-mux fanout.
(* keep_hierarchy = 1 *)
module rv32_axi_response_field #(
    parameter integer WIDTH=16,DEPTH=2,PW=$clog2(DEPTH)
) (
    input wire clock,reset,push_i,pop_i,
    input wire [WIDTH-1:0] data_i,
    output wire [WIDTH-1:0] data_o
);
    reg [WIDTH-1:0] rows [0:DEPTH-1];
    reg [PW-1:0] read_row,write_row;
    always @(posedge clock) begin
        if(reset) begin read_row<=0;write_row<=0;end
        else begin
            if(push_i) begin rows[write_row]<=data_i;write_row<=write_row+1'b1;end
            if(pop_i) read_row<=read_row+1'b1;
        end
    end
    assign data_o=rows[read_row];
endmodule
'''

def transform(text):
    start=text.index('module rv32_axi_response_fifo #(')
    before,part=text[:start],text[start:]
    part=part.replace('    reg [WIDTH-1:0] packets [0:DEPTH-1];\n','',1)
    part=part.replace('    reg [PTR_WIDTH-1:0] head, tail;\n','',1)
    part=part.replace('    assign out_packet = packets[head];\n','',1)
    part=part.replace('            head <= 0; tail <= 0; count <= 0;','            count <= 0;',1)
    old=r'''            if (push) begin
                packets[tail] <= in_packet;
                tail <= tail + 1'b1;
            end
            if (pop) head <= head + 1'b1;'''
    assert part.count(old)==1
    part=part.replace(old,'',1)
    banks=r'''
    genvar field;
    generate for(field=0;field<(WIDTH+15)/16;field=field+1) begin:g_payload_field
        localparam integer FIELD_WIDTH=(WIDTH-field*16<16)?WIDTH-field*16:16;
        rv32_axi_response_field #(.WIDTH(FIELD_WIDTH),.DEPTH(DEPTH)) bank (
            .clock(clock),.reset(reset),.push_i(push),.pop_i(pop),
            .data_i(in_packet[field*16 +: FIELD_WIDTH]),
            .data_o(out_packet[field*16 +: FIELD_WIDTH]));
    end endgenerate
'''
    anchor='    initial begin\n        if (WIDTH < 1 || DEPTH < 2'
    assert part.count(anchor)==1
    part=part.replace(anchor,banks+'\n'+anchor,1)
    return before+part+FIELD

def main():
    assert not STAGE.exists(),'Preserve previous candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for n,h in manifest['source_sha256'].items():
        assert sha(BASE/n)==h.lower(),n
        p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/n,p)
    name='rtl/course/rv32_axi_lite_bridge.v';p=STAGE/name
    p.write_text(transform(p.read_text(encoding='utf-8')),encoding='utf-8')
    manifest['changed'].append(dict(file=name,change='Response word FIFOs own payload and local pointers, no added latency'))
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},tool_sha256=sha(__file__),
        strategy=manifest['strategy']+'; AXI response payload fields own local FIFO pointers at the existing boundary')
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True)))

if __name__=='__main__':main()
