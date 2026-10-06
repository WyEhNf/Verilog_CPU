"""Prepare a source-only alternative to the measured DM1 inputs."""
import hashlib
import json
from pathlib import Path
import difflib
from prepare_staged_frequency_candidate import ROOT, change, prepare


def registered_probe(text):
    text=change(text,'    parameter integer WAKE_MUX_IMPL = 0,',
        '''    parameter integer WAKE_MUX_IMPL = 0,
    // Only the read-only store-address probe uses saved operands. Ordinary
    // issue continues to fold current-cycle wakeups into both operands.
    parameter integer REGISTERED_BASE_PROBE = 0,''')
    text=change(text,
        '    // A read-only view of the existing base operand, including CDB bypass.',
        '''    // A read-only base operand view. REGISTERED_BASE_PROBE separates
    // the opportunistic address probe from current-cycle CDB bypass.''')
    return change(text,
        '''            assign entry_base_ready_o[entry_index] = valid_mem[entry_index] &&
                target_live_mem[entry_index] && src1_ready_effective[entry_index] &&
                !flush_valid_i;
            assign entry_base_value_o[(entry_index*32) +: 32] = src1_value_effective[entry_index];''',
        '''            wire probe_base_ready=(REGISTERED_BASE_PROBE!=0) ?
                src1_ready_mem[entry_index] : src1_ready_effective[entry_index];
            assign entry_base_ready_o[entry_index] = valid_mem[entry_index] &&
                target_live_mem[entry_index] && probe_base_ready && !flush_valid_i;
            assign entry_base_value_o[(entry_index*32) +: 32] =
                (REGISTERED_BASE_PROBE!=0) ? src1_value_mem[entry_index] :
                    src1_value_effective[entry_index];''')


def backend(text):
    return change(text,'.WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL), .AGE_ORDER_MATRIX(2),',
        '.WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL), .REGISTERED_BASE_PROBE(STORE_RS_LINKS), .AGE_ORDER_MATRIX(2),')


if __name__=='__main__':
    parent=ROOT/'DM1_lsq_report_bound_widths'
    transforms={'rtl/backend/rv32_reservation_station.v':registered_probe,
                'rtl/backend/rv32_backend_joint.v':backend}
    original=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    for name,expected in original['source_sha256'].items():
        assert hashlib.sha256((parent/name).read_bytes()).hexdigest()==expected,name
    out=prepare('DN_store_registered_probe',parent,transforms,
        'DM1 alternative: existing registered RS operands for linked early store probe only; '
        'ordinary wake/issue bypass and normal ALU LSQ updates unchanged. Source-only, untested, not adopted.')
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest['actual_preparation_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['changed_files_vs_parent']=list(transforms)
    manifest['declared_additional_state_bits_vs_parent']=0
    manifest['timing_tradeoff']='Removes same-cycle wake from early probe; may delay store-address availability, not ordinary issue.'
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    patch=''.join(''.join(difflib.unified_diff(
        (parent/name).read_text(encoding='utf-8').splitlines(keepends=True),
        (out/name).read_text(encoding='utf-8').splitlines(keepends=True),
        fromfile=parent.name+'/'+name,tofile=out.name+'/'+name)) for name in transforms)
    (out/'changes_vs_DM1.patch').write_text(patch,encoding='utf-8')
