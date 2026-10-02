"""Isolate actual RS allocation-only state in at-most-32-bit functional banks.

Keep operand wake/ready/valid ownership and all execution cycles unchanged.
This prototype targets measured allocation-control fanout; only actual state
owners keep hierarchy. No buffer stubs, SRAM substitutions or CPU integration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

HELPER = r'''
// Owns actual RS payload state, local allocation decode and lane selection.
// Reset-less fields retain their original undefined value until allocation.
(* keep_hierarchy = 1 *)
module rv32_rs_allocation_payload_bank #(
    parameter integer WIDTH = 32,
    parameter integer BE_WIDTH = 4,
    parameter integer SLOT_WIDTH = 4,
    parameter integer ROW_ID = 0,
    parameter integer RESET_ZERO = 0
) (
    input wire clk_i, reset_i, flush_i,
    input wire [BE_WIDTH-1:0] alloc_fire_i,
    input wire [BE_WIDTH*SLOT_WIDTH-1:0] alloc_slots_i,
    input wire [BE_WIDTH*WIDTH-1:0] alloc_data_i,
    output reg [WIDTH-1:0] data_o
);
    wire [BE_WIDTH-1:0] selected, granted;
    genvar lane;
    generate for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin : g_lane
        assign selected[lane] = alloc_fire_i[lane] &&
            alloc_slots_i[lane*SLOT_WIDTH +: SLOT_WIDTH] == ROW_ID;
        if (lane == BE_WIDTH-1) assign granted[lane] = selected[lane];
        else assign granted[lane] = selected[lane] && !(|selected[BE_WIDTH-1:lane+1]);
    end endgenerate
    reg [WIDTH-1:0] data_next;
    integer mux_lane;
    always @* begin
        data_next = 0;
        for (mux_lane = 0; mux_lane < BE_WIDTH; mux_lane = mux_lane + 1)
            data_next = data_next | ({WIDTH{granted[mux_lane]}} &
                                     alloc_data_i[mux_lane*WIDTH +: WIDTH]);
    end
    always @(posedge clk_i) begin
        if (reset_i) begin
            if (RESET_ZERO != 0) data_o <= 0;
        end else if (!flush_i && (|selected)) begin
            data_o <= data_next;
        end
    end
endmodule
'''


def replace(text, old, new):
    assert text.count(old) == 1, 'Ambiguous anchor: '+old
    return text.replace(old,new)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root',required=True,type=Path)
    parser.add_argument('--outdir',required=True,type=Path)
    args=parser.parse_args()
    source=args.original_root.resolve()/'rtl/backend/rv32_reservation_station.v'
    out=args.outdir.resolve()
    assert not out.exists()
    original=source.read_text()
    text=replace(original,'    parameter integer ALLOC_STATIC_WRITE = 0,',
        '    parameter integer ALLOC_STATIC_WRITE = 0,\n'
        '    parameter integer ALLOC_PAYLOAD_BANKS = 0,')
    # Field order exactly matches the existing packed allocation payload, LSB first.
    fields=[('age','AGE_WIDTH'),('metadata','METADATA_WIDTH'),('store_data','STORE_DATA_WIDTH'),
            ('src2_ready','1'),('src2_tag','TAG_WIDTH'),('src2_value','32'),
            ('src1_ready','1'),('src1_tag','TAG_WIDTH'),('src1_value','32'),
            ('phys_rd','PHYS_ADDR_WIDTH'),('rob_tag','TAG_WIDTH'),('pc','32'),
            ('op','OP_WIDTH'),('target_live','1')]
    banked={'age','metadata','store_data','src2_tag','src1_tag','phys_rd','rob_tag','pc','op'}
    body=text.index('    always @(posedge clk_i) begin')
    head,seq=text[:body],text[body:]
    for field,width in fields:
        if field not in banked:
            continue
        pattern=rf'    reg (\[[^\n]+\]) {field}_mem \[0:ENTRIES-1\];'
        match=re.search(pattern,head)
        assert match
        head=replace(head,match[0],f'    reg {match[1]} legacy_{field}_mem [0:ENTRIES-1];\n'
                                   f'    wire {match[1]} {field}_mem [0:ENTRIES-1];')
        for index in ['alloc_slot','alloc_static_row']+(['reset_slot'] if field=='age' else []):
            old=f'{field}_mem[{index}]'
            assert seq.count(old)==1,(field,index)
            seq=seq.replace(old,'legacy_'+old)
    lines=['    // Bank-owned allocation fields retain root read-only state aliases.',
           '    genvar payload_row, payload_chunk, payload_lane;',
           '    generate for (payload_row = 0; payload_row < ENTRIES; payload_row = payload_row + 1) begin : g_payload_state',
           '        if (ALLOC_PAYLOAD_BANKS != 0 && ALLOC_STATIC_WRITE != 0) begin : g_banks',
           '            wire [BE_WIDTH*SLOT_WIDTH-1:0] slots;',
           '            for (payload_lane = 0; payload_lane < BE_WIDTH; payload_lane = payload_lane + 1) begin : g_slots',
           '                assign slots[payload_lane*SLOT_WIDTH +: SLOT_WIDTH] = allocation_slots[payload_lane];',
           '            end']
    offset=[]
    for field,width in fields:
        if field in banked:
            off=' + '.join(offset) if offset else '0'
            lines += [f'            for (payload_chunk = 0; payload_chunk < ({width}+31)/32; payload_chunk = payload_chunk + 1) begin : g_{field}',
                      f'                localparam integer CHUNK_WIDTH = ({width}-payload_chunk*32 < 32) ? {width}-payload_chunk*32 : 32;',
                      '                wire [BE_WIDTH*CHUNK_WIDTH-1:0] lane_data;',
                      '                for (payload_lane = 0; payload_lane < BE_WIDTH; payload_lane = payload_lane + 1) begin : g_data',
                      f'                    assign lane_data[payload_lane*CHUNK_WIDTH +: CHUNK_WIDTH] = alloc_lane_payload[payload_lane][({off})+payload_chunk*32 +: CHUNK_WIDTH];',
                      '                end',
                      '                rv32_rs_allocation_payload_bank #(.WIDTH(CHUNK_WIDTH), .BE_WIDTH(BE_WIDTH),',
                      f'                    .SLOT_WIDTH(SLOT_WIDTH), .ROW_ID(payload_row), .RESET_ZERO({1 if field=="age" else 0})) state_bank (',
                      '                    .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_valid_i),',
                      '                    .alloc_fire_i(alloc_fire_o), .alloc_slots_i(slots), .alloc_data_i(lane_data),',
                      f'                    .data_o({field}_mem[payload_row][payload_chunk*32 +: CHUNK_WIDTH]));',
                      '            end']
        offset.append(width)
    lines += ['        end else begin : g_legacy']
    lines += [f'            assign {field}_mem[payload_row] = legacy_{field}_mem[payload_row];' for field,_ in fields if field in banked]
    lines += ['        end','    end endgenerate','']
    text=head+'\n'.join(lines)+'\n'+seq+HELPER
    target=out/'rtl/backend/rv32_reservation_station.v'
    target.parent.mkdir(parents=True)
    target.write_text(text)
    (out/'baseline.v').write_bytes(source.read_bytes())
    manifest=dict(status='PREPARED',source=str(source),source_sha256=sha(source),candidate_sha256=sha(target),
                  description=__doc__,parameters={'ALLOC_PAYLOAD_BANKS':0},bank_width_max=32,
                  banked_fields=sorted(banked),added_pipeline_cycles=0,cpu_integrated=False,claims_cpu_ppa=False)
    (out/'candidate_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    main()
