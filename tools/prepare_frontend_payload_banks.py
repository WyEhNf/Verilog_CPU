"""Isolate real fetch-queue payload state to reduce local write-control loads.

Preserve response chaining, reset values, redirect behavior and all cycles.
Functional banks own actual state and lane selection; no buffer-only modules.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(code,before,after):
    assert code.count(before)==1, 'Ambiguous anchor: '+before[:100]
    return code.replace(before,after)


HELPER=r'''
// Each bank owns an actual queue field and its local write selection.
(* keep_hierarchy = 1 *)
module rv32_frontend_queue_payload_bank #(
    parameter integer WIDTH=32,
    parameter integer FE_WIDTH=4,
    parameter integer PTR_WIDTH=4,
    parameter integer ROW_ID=0
) (
    input wire clk_i, reset_i, redirect_i,
    input wire [FE_WIDTH-1:0] write_valid_i,
    input wire [FE_WIDTH*PTR_WIDTH-1:0] write_slots_i,
    input wire [FE_WIDTH*WIDTH-1:0] write_data_i,
    output reg [WIDTH-1:0] data_o
);
    wire [FE_WIDTH-1:0] selected, granted;
    genvar lane;
    generate for(lane=0;lane<FE_WIDTH;lane=lane+1) begin:g_lane
        assign selected[lane]=write_valid_i[lane] &&
            write_slots_i[lane*PTR_WIDTH +: PTR_WIDTH]==ROW_ID;
        if(lane==FE_WIDTH-1) assign granted[lane]=selected[lane];
        else assign granted[lane]=selected[lane] && !(|selected[FE_WIDTH-1:lane+1]);
    end endgenerate
    reg [WIDTH-1:0] packet;
    integer source_lane;
    always @* begin
        packet=0;
        for(source_lane=0;source_lane<FE_WIDTH;source_lane=source_lane+1)
            packet=packet | ({WIDTH{granted[source_lane]}} & write_data_i[source_lane*WIDTH +: WIDTH]);
    end
    always @(posedge clk_i) begin
        if(reset_i) data_o<=0;
        else if(!redirect_i && (|selected)) data_o<=packet;
    end
endmodule
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    source=args.source_root.resolve()/'rtl/frontend/rv32_fetch_frontend.v'
    out=args.outdir.resolve()
    assert not out.exists()
    original=source.read_text(encoding='utf-8')
    assert 'RESPONSE_CHAINING' not in original, 'Use the unchanged response-chaining baseline'
    code=replace(original,'    parameter integer PREDICTOR_META = 0',
                 '    parameter integer QUEUE_PAYLOAD_BANKS = 0,\n    parameter integer PREDICTOR_META = 0')
    fields=[('fq_pc','32','bundle_pc'),('fq_inst','32','bundle_inst'),
            ('fq_pred_taken','1','bundle_pred_taken'),('fq_pred_target','32','bundle_pred_target'),
            ('fq_pred_kind','2','bundle_pred_kind'),('fq_pred_btb_hit','1','bundle_pred_btb_hit'),
            ('fq_epoch','EPOCH_WIDTH','{FE_WIDTH{bundle_epoch}}'),
            ('fq_pred_metadata','16',"((PREDICTOR_META != 0) ? if_resp_pred_metadata_i : {FE_WIDTH*16{1'b0}})")]
    for name,width,bus in fields:
        pattern=r'    reg (\[[^\n]+?\] )?'+name+r' \[0:FQ_DEPTH-1\];'
        matches=list(re.finditer(pattern,code));assert len(matches)==1
        packed=matches[0].group(1) or ''
        code=code[:matches[0].start()]+f'    wire {packed}{name} [0:FQ_DEPTH-1];\n    reg {packed}legacy_{name} [0:FQ_DEPTH-1];'+code[matches[0].end():]
        code=re.sub(r'\b'+name+r'(\[[^\n]+?\]\s*<=)',r'legacy_'+name+r'\1',code)
    reset_start=code.index('            for (k = 0; k < FQ_DEPTH; k = k + 1) begin')
    reset_end=code.index('        end else begin\n            event_fetch_o',reset_start)
    code=code[:reset_start]+'            if (QUEUE_PAYLOAD_BANKS == 0) begin\n'+code[reset_start:reset_end]+'            end\n'+code[reset_end:]
    write_start=code.index('                    for (i = 0; i < FE_WIDTH; i = i + 1) begin')
    write_end=code.index('                    tail_reg <= tail_reg + bundle_count;',write_start)
    code=code[:write_start]+'                    if (QUEUE_PAYLOAD_BANKS == 0) begin\n'+code[write_start:write_end]+'                    end\n'+code[write_end:]
    banks=['    wire [FE_WIDTH-1:0] payload_write_valid;',
           '    wire [FE_WIDTH*PTR_WIDTH-1:0] payload_write_slots;',
           '    genvar payload_lane, payload_row;',
           '    generate',
           '        for(payload_lane=0;payload_lane<FE_WIDTH;payload_lane=payload_lane+1) begin:g_payload_lane',
           '            assign payload_write_valid[payload_lane]=resp_fire && (payload_lane<bundle_count);',
           '            assign payload_write_slots[payload_lane*PTR_WIDTH +: PTR_WIDTH]=tail_reg+payload_lane;',
           '        end',
           '        for(payload_row=0;payload_row<FQ_DEPTH;payload_row=payload_row+1) begin:g_payload_row',
           '            if(QUEUE_PAYLOAD_BANKS != 0) begin:g_banks']
    for name,width,bus in fields:
        banks += [f'                rv32_frontend_queue_payload_bank #(.WIDTH({width}), .FE_WIDTH(FE_WIDTH),',
                  f'                    .PTR_WIDTH(PTR_WIDTH), .ROW_ID(payload_row)) {name}_bank (',
                  '                    .clk_i(clk_i), .reset_i(reset_i), .redirect_i(redirect_valid_i),',
                  '                    .write_valid_i(payload_write_valid), .write_slots_i(payload_write_slots),',
                  f'                    .write_data_i({bus}), .data_o({name}[payload_row]));']
    banks += ['            end else begin:g_legacy']
    banks += [f'                assign {name}[payload_row]=legacy_{name}[payload_row];' for name,_,_ in fields]
    banks += ['            end','        end','    endgenerate','']
    code=replace(code,'    assign current_epoch_o = epoch_reg;', '\n'.join(banks)+'\n    assign current_epoch_o = epoch_reg;')
    code=replace(code,'    initial begin\n','    initial begin\n        if(QUEUE_PAYLOAD_BANKS != 0 && QUEUE_PAYLOAD_BANKS != 1)\n            $fatal(1, "Invalid frontend payload bank mode");\n')
    code+=HELPER
    tb=(ROOT/'tb/unit/rv32_fetch_frontend_tb.v').read_text()
    tb=replace(tb,'.PREDICTOR_META(PREDICTOR_META)) dut (',
               '.PREDICTOR_META(PREDICTOR_META), .QUEUE_PAYLOAD_BANKS(1)) dut (')
    tb=replace(tb,'    integer cycle;','    initial if(dut.QUEUE_PAYLOAD_BANKS != 1) $fatal(1, "Payload banks not enabled");\n    integer cycle;')
    probe=(ROOT/'tools/probe_localized_component.py').read_text()
    probe=replace(probe,"choices=('dcache','rob','rs')", "choices=('dcache','rob','rs','frontend')")
    probe=replace(probe,"('rtl/backend/rv32_reservation_station.v',) if args.component == 'rs' else", "('rtl/backend/rv32_reservation_station.v',) if args.component == 'rs' else\n        ('rtl/frontend/rv32_fetch_frontend.v',) if args.component == 'frontend' else")
    probe=replace(probe,"        case.mkdir()", "        if args.component == 'frontend':\n            case = out/f'payload_banks{variant}'\n        case.mkdir()")
    probe=replace(probe,"        else:\n            root_module = 'rv32_rob'", "        elif args.component == 'frontend':\n            root_module = 'rv32_fetch_frontend'\n            parameters = dict(FE_WIDTH=4,FQ_DEPTH=16,EPOCH_WIDTH=4,PREDICTOR_META=0,QUEUE_PAYLOAD_BANKS=variant)\n        else:\n            root_module = 'rv32_rob'")
    files={'rtl/frontend/rv32_fetch_frontend.v':code,'tb/unit/rv32_fetch_frontend_tb.v':tb,
           'tools/probe_localized_component.py':probe}
    for name,contents in files.items():
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(contents)
    baseline=out/'baseline/rv32_fetch_frontend.v';baseline.parent.mkdir(parents=True);baseline.write_bytes(source.read_bytes())
    assert sha(source)==sha(baseline)
    report=dict(status='PREPARED',source=str(source),baseline_sha256=sha(source),
                candidate_sha256=sha(out/'rtl/frontend/rv32_fetch_frontend.v'),
                files_sha256={name:sha(out/name) for name in files},all_original_fields_preserved=True,
                extra_execution_cycles=0,response_chaining_unchanged=True,integrated_into_cpu=False)
    (out/'candidate_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
