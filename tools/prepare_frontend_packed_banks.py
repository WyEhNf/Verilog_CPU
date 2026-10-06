"""Share row decode across all real fetch packet fields in one state bank.

Based on the verified field-bank candidate, this reduces replicated selection
logic while retaining the same queue fields, reset behavior and cycles.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field-candidate', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    old, out = args.field_candidate.resolve(), args.outdir.resolve()
    assert not out.exists()
    manifest = json.loads((old/'candidate_manifest.json').read_text())
    for name, value in manifest['files_sha256'].items():
        assert sha(old/name) == value
    assert sha(old/'baseline/rv32_fetch_frontend.v') == manifest['baseline_sha256']
    code = (old/'rtl/frontend/rv32_fetch_frontend.v').read_text()
    start = code.index('                rv32_frontend_queue_payload_bank #(.WIDTH(32)')
    end = code.index('            end else begin:g_legacy', start)
    code = code[:start] + '''                rv32_frontend_queue_payload_bank #(.WIDTH(PAYLOAD_WIDTH), .FE_WIDTH(FE_WIDTH),
                    .PTR_WIDTH(PTR_WIDTH), .ROW_ID(payload_row)) packet_bank (
                    .clk_i(clk_i), .reset_i(reset_i), .redirect_i(redirect_valid_i),
                    .write_valid_i(payload_write_valid), .write_slots_i(payload_write_slots),
                    .write_data_i(payload_write_packets),
                    .data_o({fq_pc[payload_row], fq_inst[payload_row], fq_pred_taken[payload_row],
                        fq_pred_target[payload_row], fq_pred_kind[payload_row], fq_pred_btb_hit[payload_row],
                        fq_epoch[payload_row], fq_pred_metadata[payload_row]}));
''' + code[end:]
    anchor = '    wire [FE_WIDTH-1:0] payload_write_valid;'
    assert code.count(anchor) == 1
    code = code.replace(anchor, '''    localparam integer PAYLOAD_WIDTH = 116 + EPOCH_WIDTH;
    wire [FE_WIDTH*PAYLOAD_WIDTH-1:0] payload_write_packets;
''' + anchor)
    anchor = '            assign payload_write_valid[payload_lane]=resp_fire && (payload_lane<bundle_count);'
    assert code.count(anchor) == 1
    code = code.replace(anchor, '''            assign payload_write_packets[payload_lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH] = {
                bundle_pc[payload_lane*32 +: 32], bundle_inst[payload_lane*32 +: 32],
                bundle_pred_taken[payload_lane], bundle_pred_target[payload_lane*32 +: 32],
                bundle_pred_kind[payload_lane*2 +: 2], bundle_pred_btb_hit[payload_lane], bundle_epoch,
                ((PREDICTOR_META != 0) ? if_resp_pred_metadata_i[payload_lane*16 +: 16] : 16'b0)};
''' + anchor)
    for name in ['baseline/rv32_fetch_frontend.v', 'tb/unit/rv32_fetch_frontend_tb.v',
                 'tools/probe_localized_component.py']:
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old/name, target)
    rtl = out/'rtl/frontend/rv32_fetch_frontend.v'
    rtl.parent.mkdir(parents=True, exist_ok=True)
    rtl.write_text(code)
    report = dict(status='PREPARED', field_candidate=str(old),
                  field_candidate_sha256=manifest['candidate_sha256'],
                  baseline_sha256=manifest['baseline_sha256'], candidate_sha256=sha(rtl),
                  files_sha256={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()},
                  packet_width='116+EPOCH_WIDTH', real_banks_per_row=1,
                  cpu_integrated=False, extra_execution_cycles=0)
    (out/'candidate_manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
