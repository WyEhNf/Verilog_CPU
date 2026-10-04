"""Exclude the saved probe owner from next selection; source-only candidate."""
import difflib
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare


def backend(text):
    text=change(text,'        wire probe_valid;',
        '''        wire probe_valid;
        wire [LSQ_ENTRIES-1:0] probe_pending;
        if(STORE_RS_LINKS!=0) begin:g_inflight_probe
            localparam integer DOMAINS=(LSQ_ENTRIES+3)/4;
            wire [DOMAINS*(TAG_WIDTH+1)-1:0] owner_views;
            rv32_frequency_control_tree #(.WIDTH(TAG_WIDTH+1),.LEAVES(DOMAINS)) owner_tree (
                .signal_i({probe_valid,shared_store_addr_tag}),.views_o(owner_views));
            for(genvar probe_row=0;probe_row<LSQ_ENTRIES;probe_row=probe_row+1) begin:g_row
                wire saved_valid=owner_views[(probe_row/4)*(TAG_WIDTH+1)+TAG_WIDTH];
                wire [TAG_WIDTH-1:0] saved_tag=owner_views[(probe_row/4)*(TAG_WIDTH+1) +: TAG_WIDTH];
                // The old packet publishes this cycle, while LSQ pending is
                // still old until the edge. Skip its full owner identity so
                // consecutive selected packets can belong to distinct stores.
                assign probe_pending[probe_row]=lsq_store_addr_pending[probe_row] &&
                    !(saved_valid && saved_tag==lsq_store_addr_lsq_tag[probe_row*TAG_WIDTH +: TAG_WIDTH]);
            end
        end else begin:g_legacy_pending
            assign probe_pending=lsq_store_addr_pending;
        end''')
    return change(text,'.head_i(lsq_head), .pending_i(lsq_store_addr_pending),',
        '.head_i(lsq_head), .pending_i(probe_pending),')


if __name__=='__main__':
    parent=ROOT/'DO_store_address_pipeline'
    original=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    for name,expected in original['source_sha256'].items():
        assert hashlib.sha256((parent/name).read_bytes()).hexdigest()==expected,name
    name='rtl/backend/rv32_backend_joint.v'
    out=prepare('DO1_store_address_inflight',parent,{name:backend},
        'DO source refinement: full saved LSQ tag excludes the in-flight probe from next selection; '
        'four-row owner distribution. Source-only, untested, not adopted.')
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        changed_files_vs_parent=[name],declared_additional_state_bits_vs_parent=0,
        declared_additional_state_bits_vs_DM1=99,
        timing_tradeoff='One store-probe cycle; skips complete identity of saved owner to avoid duplicate pending selections.')
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    base=ROOT/'DM1_lsq_report_bound_widths'
    patch=''.join(difflib.unified_diff((base/name).read_text(encoding='utf-8').splitlines(keepends=True),
        (out/name).read_text(encoding='utf-8').splitlines(keepends=True),
        fromfile=base.name+'/'+name,tofile=out.name+'/'+name))
    (out/'changes_vs_DM1.patch').write_text(patch,encoding='utf-8')
