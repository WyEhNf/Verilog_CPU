"""Match ROB completion distribution to enabled field owners; source only."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A9_unconnected_return_payload'
TARGET=BASE/'A10_compact_rob_completion'
FIELDS=['value','addr','data','mask','mmio']


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def layout(mmio_predecode,legacy_halt,returned_data):
    return [field for field in FIELDS if
        field=='mmio' or
        (field=='value' and legacy_halt) or
        (field in ('addr','mask') and not mmio_predecode) or
        (field=='data' and returned_data)]


def input_field(field):
    if field=='mmio':return 'mmio'
    names=dict(value='completion_value_i',addr='completion_store_addr_i',
               data='completion_store_data_i',mask='completion_store_mask_i')
    width=4 if field=='mask' else 32
    return f'{names[field]}[command_lane*{width} +: {width}]'


def payload_expr(fields,output=False):
    return '{'+','.join(('completed_'+f if output else input_field(f)) for f in fields)+'}'


def layout_tree(output=False):
    chunks=[]
    for mmio in (False,True):
        chunks.append('            '+('if(MMIO_PREDECODE==0)' if not mmio else 'else')+f' begin:g_mmio_{int(mmio)}')
        for halt in (True,False):
            chunks.append('                '+('if(LEGACY_HALT_PAYLOAD!=0)' if halt else 'else')+f' begin:g_halt_{int(halt)}')
            for ret in (True,False):
                chunks.append('                    '+('if(RETURN_VALUE_ENABLE!=0)' if ret else 'else')+f' begin:g_return_{int(ret)}')
                fields=layout(mmio,halt,ret)
                if output:
                    chunks.append('                        assign '+payload_expr(fields,True)+'=completion_mux[1];')
                    for field in FIELDS:
                        if field not in fields:
                            width=4 if field=='mask' else 32
                            chunks.append(f"                        assign completed_{field}={width}'b0;")
                else:chunks.append('                        assign compact_data='+payload_expr(fields)+';')
                chunks.append('                    end')
            chunks.append('                end')
        chunks.append('            end')
    return '\n'.join(chunks)


def main():
    assert not TARGET.exists(),TARGET
    pm=read(PARENT/'candidate.json')
    for name,digest in pm['source_sha256'].items():assert sha(PARENT/name)==digest,name
    name='rtl/backend/rv32_rob.v';old=(PARENT/name).read_text(encoding='utf-8');text=old
    text=once(text,'    localparam integer LOCAL_COMPLETION_DATA_WIDTH=101;',
        '''    // Removed field owners must also leave their broadcast/mux lanes.
    localparam integer COMPLETION_KEEP_VALUE=(LIGHT_RETIRE_PAYLOAD==0) || (LEGACY_HALT_PAYLOAD!=0);
    localparam integer COMPLETION_KEEP_ADDRESS=(LIGHT_RETIRE_PAYLOAD==0) || (MMIO_PREDECODE==0);
    localparam integer COMPLETION_KEEP_DATA=(LIGHT_RETIRE_PAYLOAD==0) || (RETURN_VALUE_ENABLE!=0);
    localparam integer LOCAL_COMPLETION_DATA_WIDTH=1+
        (COMPLETION_KEEP_VALUE?32:0)+(COMPLETION_KEEP_ADDRESS?36:0)+(COMPLETION_KEEP_DATA?32:0);''')
    anchor='''            assign local_completion_input[command_lane*LOCAL_COMPLETION_WIDTH +: LOCAL_COMPLETION_WIDTH]={
                completion_valid_i[command_lane],completion_done_i[command_lane],
                completion_error_i[command_lane],completion_tag_i[command_lane*TAG_WIDTH +: TAG_WIDTH],
                completion_value_i[command_lane*32 +: 32],
                completion_store_addr_i[command_lane*32 +: 32],
                completion_store_data_i[command_lane*32 +: 32],
                completion_store_mask_i[command_lane*4 +: 4],mmio};'''
    replacement=f'''            wire [LOCAL_COMPLETION_DATA_WIDTH-1:0] compact_data;
            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_completion
                assign compact_data={payload_expr(FIELDS)};
            end else begin:g_light_completion
{layout_tree()}
            end
            assign local_completion_input[command_lane*LOCAL_COMPLETION_WIDTH +: LOCAL_COMPLETION_WIDTH]={{
                completion_valid_i[command_lane],completion_done_i[command_lane],
                completion_error_i[command_lane],completion_tag_i[command_lane*TAG_WIDTH +: TAG_WIDTH],compact_data}};'''
    text=once(text,anchor,replacement)
    anchor='''            assign {completed_value,completed_addr,completed_data,completed_mask,completed_mmio}=completion_mux[1];'''
    replacement=f'''            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_completed_fields
                assign {payload_expr(FIELDS,True)}=completion_mux[1];
            end else begin:g_light_completed_fields
{layout_tree(True)}
            end'''
    text=once(text,anchor,replacement)
    assert blocks(text)==blocks(old)
    # All unchanged behavioral predicates and the exact late-lane OR priority
    # remain as source text. Layout deletion/reinsertion only drops owners
    # which already produced constants in A9.
    for region in ('assign completion_match[command_lane]',
                   'assign completion_errors[command_lane]',
                   'wire completed=|completion_match;',
                   'wire acknowledged=normal && ack_valid && tag_matches(ack_tag,command_row);'):
        assert region in old and region in text
    for name in pm['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    (TARGET/'rtl/backend/rv32_rob.v').write_text(text,encoding='utf-8')
    record=dict(pm)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=['rtl/backend/rv32_rob.v'],
        source_sha256={n:sha(TARGET/n) for n in pm['source_sha256']},preparation_script_sha256=sha(Path(__file__)))
    record['enabled_profile']=dict(pm['enabled_profile'],rob_completion_data_bits=1,
        rob_completion_packet_bits=20,rob_completion_select_words=1)
    record['implemented_changes']=list(pm['implemented_changes'])+[
        'Compact ROB completion broadcast and per-row selection to the enabled field owners; current profile carries only the MMIO result bit plus original valid/done/error/full tag.'
    ]
    record['material_gain_evidence']=dict(pm['material_gain_evidence'],
        rob_completion_data_width_before=101,rob_completion_data_width_after=1,
        rob_completion_broadcast_width_before=480,rob_completion_broadcast_width_after=80,
        completion_grant_word_leaves_before=896,completion_grant_word_leaves_after=128,
        completion_distribution_only_no_extra_cycles=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_PACKET_PROJECTION_ONLY_NOT_FULL_CORE_PROOF',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=record['changed_from_parent_files'],new_state_bits=0,added_pipeline_cycles=0,
        source_clocked_blocks_text_equal=True,tests_started=False,adopted=False,
        layouts=[dict(mmio_predecode=m,legacy_halt=h,return_value=r,fields=layout(m,h,r))
                 for m in (False,True) for h in (False,True) for r in (False,True)],
        source_argument=[
            'Default LIGHT_RETIRE_PAYLOAD=0 retains the exact original 101bit value/address/storedata/mask/mmio ordering.',
            'Each light configuration includes precisely fields whose owners remain in A9; input layouts and output layouts are generated from the same ordered list.',
            'A9 absent owners already drive constant zero. The restored command values therefore have the same observable consumers.',
            'MMIO predicate is computed from the same incoming address/mask before compacting; its qualification by completion full tag/done/error/recovery is unchanged.',
            'The high-lane grant priority, padding, bitwise AND/OR reduction and normal/recovery/allocation/reset precedence remain unchanged.',
            'Deletion/reinsertion of unconsumed coordinates commutes with the AND/OR packet selection even with zero or multiple input matches.',
            'No valid/ready/gen/error, store admission/ack, return/halt timing or in-order commit predicate changes.',
            'Reduction in kept control-tree width/leaves is source-level evidence; actual mapped area/timing remain unknown.'
        ])
    write(BASE/'A10_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','new_state_bits','tests_started')})


if __name__=='__main__':main()
