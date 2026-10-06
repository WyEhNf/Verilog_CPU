"""Compact unused direct CDB payload without changing selection or locked tags."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A10_compact_rob_completion'
TARGET=BASE/'A11_compact_direct_cdb'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def replace_between(text,start,end,new):
    assert text.count(start)==1,start
    first=text.index(start);last=text.index(end,first)
    return text[:first]+new+text[last:]


def expression(branch,store):
    fields=[
        'producer_tag_i[payload_source*TAG_WIDTH +: TAG_WIDTH]',
        'producer_phys_rd_i[payload_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]',
        'producer_rd_we_i[payload_source] && !producer_is_store_i[payload_source]',
        'producer_is_store_i[payload_source]']
    if branch:fields += ['producer_is_branch_i[payload_source]',
        'producer_branch_taken_i[payload_source]','producer_redirect_valid_i[payload_source]']
    fields += ['producer_is_memory_i[payload_source]','producer_is_load_i[payload_source]',
        'producer_value_i[payload_source*32 +: 32]','producer_addr_i[payload_source*32 +: 32]']
    if store:fields.append('producer_store_data_i[payload_source*32 +: 32]')
    if branch:fields.append('producer_branch_target_i[payload_source*32 +: 32]')
    return '{'+',\n                        '.join(fields)+'}'


def packing():
    lines=[]
    for branch in (True,False):
        lines.append('                '+('if(DIRECT_BRANCH_PAYLOAD!=0)' if branch else 'else')+f' begin:g_branch_{int(branch)}')
        for store in (True,False):
            lines.append('                    '+('if(DIRECT_STORE_PAYLOAD!=0)' if store else 'else')+f' begin:g_store_{int(store)}')
            lines.append('                        assign data='+expression(branch,store)+';')
            lines.append('                    end')
        lines.append('                end')
    return '\n'.join(lines)


def unpacking():
    # Expanded metadata retains its original tag offset and lock interface.
    # Compact packet ordering is identical to the input packing above.
    leaf='RANK_LEAVES+payload_source'
    lines=[]
    for branch in (True,False):
        lines.append('                '+('if(DIRECT_BRANCH_PAYLOAD!=0)' if branch else 'else')+f' begin:g_selected_branch_{int(branch)}')
        meta=f'meta_tree[{leaf}]'
        if not branch:
            lines += ['                    wire [TAG_WIDTH-1:0] selected_tag;',
                      '                    wire [PHYS_ADDR_WIDTH-1:0] selected_phys;',
                      '                    wire selected_rd_we,selected_store,selected_memory,selected_load;',
                      f"                    assign {meta}={{selected_tag,selected_phys,selected_rd_we,selected_store,3'b0,selected_memory,selected_load}};",
                      f'                    assign target_tree[{leaf}]=0;']
            meta='selected_tag,selected_phys,selected_rd_we,selected_store,selected_memory,selected_load'
        for store in (True,False):
            lines.append('                    '+('if(DIRECT_STORE_PAYLOAD!=0)' if store else 'else')+f' begin:g_selected_store_{int(store)}')
            fields=[meta,f'value_tree[{leaf}]',f'memory_tree[{leaf}]' if store else f'memory_tree[{leaf}][63:32]']
            if branch:fields.append(f'target_tree[{leaf}]')
            lines.append('                        assign {'+','.join(fields)+'}=selected_data;')
            if not store:lines.append(f'                        assign memory_tree[{leaf}][31:0]=0;')
            lines.append('                    end')
        lines.append('                end')
    return '\n'.join(lines)


def main():
    assert not TARGET.exists(),TARGET
    pm=read(PARENT/'candidate.json')
    for name,digest in pm['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_backend_joint.v';old=(PARENT/name).read_text(encoding='utf-8');text=old
    ignored=['cdb_branch_target','cdb_is_branch','cdb_branch_taken','cdb_redirect_valid']
    for signal in ignored:assert len(re.findall(r'\b'+signal+r'\b',old))==2,signal
    text=once(text,'.BYPASS(COMPLETION_BYPASS)',
        '''.BYPASS(COMPLETION_BYPASS), .DIRECT_BRANCH_PAYLOAD(0),
        .DIRECT_STORE_PAYLOAD((LIGHT_RETIRE_PAYLOAD==0) || (ROB_RETURN_VALUE_ENABLE!=0))''')
    changes[name]=text
    name='rtl/backend/rv32_completion_network.v';old=(PARENT/name).read_text(encoding='utf-8');text=old
    text=once(text,'    parameter integer BYPASS = 0,',
        '''    parameter integer BYPASS = 0,
    // These optional direct-mode fields may be omitted only by a caller
    // which does not consume the corresponding CDB outputs. Legacy FIFO
    // paths and the standalone defaults retain their complete payload.
    parameter integer DIRECT_BRANCH_PAYLOAD = 1,
    parameter integer DIRECT_STORE_PAYLOAD = 1,''')
    text=once(text,'localparam integer DATA_WIDTH=DIRECT_META_WIDTH+128;',
        '''localparam integer DATA_WIDTH=TAG_WIDTH+PHYS_ADDR_WIDTH+4+64+
                    ((DIRECT_BRANCH_PAYLOAD!=0)?35:0)+((DIRECT_STORE_PAYLOAD!=0)?32:0);''')
    text=replace_between(text,'                wire [DATA_WIDTH-1:0] data={',
        '\n                wire [DATA_WIDTH-1:0] selected_data;',
        '                wire [DATA_WIDTH-1:0] data;\n'+packing())
    text=replace_between(text,'                assign meta_tree[RANK_LEAVES+payload_source]=selected_data[128',
        '\n            end else begin:g_zero',unpacking())
    changes[name]=text
    for name,text in changes.items():assert blocks(text)==blocks((PARENT/name).read_text(encoding='utf-8')),name
    for name in pm['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(pm)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in pm['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)))
    record['enabled_profile']=dict(pm['enabled_profile'],DIRECT_BRANCH_PAYLOAD=0,DIRECT_STORE_PAYLOAD=0,
        direct_cdb_selection_packet_bits=90,direct_cdb_selection_words=6)
    record['implemented_changes']=list(pm['implemented_changes'])+[
        'Drop caller-unused branch target/flags and unused ROB return-store data from direct CDB selection; retain original expanded metadata/tag lock offsets.'
    ]
    record['material_gain_evidence']=dict(pm['material_gain_evidence'],
        direct_cdb_selection_width_before=157,direct_cdb_selection_width_after=90,
        direct_cdb_control_word_leaves_before=180,direct_cdb_control_word_leaves_after=108)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_PACKET_PROJECTION_ONLY_NOT_FULL_CORE_PROOF',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=list(changes),new_state_bits=0,added_pipeline_cycles=0,
        source_clocked_blocks_text_equal=True,tests_started=False,adopted=False,
        ignored_branch_signals=ignored,
        source_argument=[
            'Each ignored CDB branch signal occurs exactly twice in the backend: declaration and completion-network connection. Branch resolution/predictor feedback consume held ALU output separately.',
            'Actual tag/phys/value/address/rdwe/store/memory/load fields retain original data and selection.',
            'Store data is omitted only when light retirement and unconnected internal return mode imply its ROB owner is absent. LSQ store bytes still use ALU exec_store_data directly.',
            'Round-robin rank, eligibility, selected_mask, source ready and lane-lock logic are unchanged.',
            'Expanded direct_meta retains its original29bit shape and tag/phys offsets; omitted branch flags are restored as zero.',
            'Standalone defaults keep all fields, and FIFO/single-CDB legacy code is untouched.',
            'All four input/output layouts match. Masking/reduction preserves every retained coordinate with zero/multiple grants as well as ordinary one-hot grants.',
            'No timing, mapped area, IPC or full-core proof is claimed for this untested source candidate.'
        ])
    write(BASE/'A11_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','new_state_bits','tests_started')})


if __name__=='__main__':main()
