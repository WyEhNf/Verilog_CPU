"""Prepare an optional course-top projection; preserve the actual AXI exit payload."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks
from prepare_er1_narrow_rob_packets import FULL, LIGHT_FALLBACK, LIGHT_MMIO, pack, unpack

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A8_direct_issue_local_recovery'
TARGET=BASE/'A9_unconnected_return_payload'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def replace_between(text,start,end,new):
    assert text.count(start)==1,start
    first=text.index(start);last=text.index(end,first)
    return text[:first]+new+text[last:]


def field_layout(mmio_predecode,halt_payload,return_payload):
    fields=list(LIGHT_MMIO if mmio_predecode else LIGHT_FALLBACK)
    if not halt_payload:fields.remove('value')
    if not return_payload:fields.remove('store_data')
    return fields


def generate_layout(indent,index,output=False):
    pieces=[]
    for mmio in (False,True):
        prefix='if' if not mmio else 'else'
        guard='(MMIO_PREDECODE==0)' if not mmio else ''
        pieces.append(f'{indent}{prefix}{guard} begin:g_mmio_{int(mmio)}')
        if output and mmio:
            pieces += [f"{indent}    assign head_store_addr[{index}]=32'b0;",
                       f"{indent}    assign head_store_mask[{index}]=4'b0;"]
        for halt in (True,False):
            prefix='if(LEGACY_HALT_PAYLOAD!=0)' if halt else 'else'
            pieces.append(f'{indent}    {prefix} begin:g_halt_{int(halt)}')
            if output and not halt:pieces.append(f"{indent}        assign head_value[{index}]=32'b0;")
            for ret in (True,False):
                prefix='if(RETURN_VALUE_ENABLE!=0)' if ret else 'else'
                pieces.append(f'{indent}        {prefix} begin:g_return_{int(ret)}')
                fields=field_layout(mmio,halt,ret)
                if output:
                    if not ret:pieces.append(f"{indent}            assign head_store_data[{index}]=32'b0;")
                    pieces.append(f'{indent}            assign {unpack(fields,index)}=head_packet[{index}];')
                else:pieces.append(f'{indent}            assign commit_row_packet[{index}]={pack(fields,index)};')
                pieces.append(f'{indent}        end')
            pieces.append(f'{indent}    end')
        pieces.append(f'{indent}end')
    return '\n'.join(pieces)


def main():
    assert not TARGET.exists(),TARGET
    pm=read(PARENT/'candidate.json')
    for name,digest in pm['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/course/student_top.v';text=(PARENT/name).read_text(encoding='utf-8')
    # There is no return_value output in the course interface. The official
    # harness observes the memory write; the LSQ/AXI payload remains intact.
    assert 'return_value' not in text
    text=once(text,'.RAM_SIZE_BYTES(268435456), .LEGACY_SENTINEL_HALT(0)',
        '.RAM_SIZE_BYTES(268435456), .LEGACY_SENTINEL_HALT(0), .RETURN_VALUE_ENABLE(0)')
    changes[name]=text
    name='rtl/cpu_core.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'parameter integer LEGACY_SENTINEL_HALT = 0,',
        '''parameter integer LEGACY_SENTINEL_HALT = 0,
    // Disable only when this diagnostic output is unconnected in the caller.
    // Architectural MMIO writes still carry the original LSQ/AXI payload.
    parameter integer RETURN_VALUE_ENABLE = 1,''')
    text=once(text,'.ROB_LEGACY_HALT_PAYLOAD(LEGACY_SENTINEL_HALT)',
        '.ROB_LEGACY_HALT_PAYLOAD(LEGACY_SENTINEL_HALT), .ROB_RETURN_VALUE_ENABLE(RETURN_VALUE_ENABLE)')
    changes[name]=text
    name='rtl/backend/rv32_backend_joint.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'parameter integer ROB_LEGACY_HALT_PAYLOAD = 1,',
        'parameter integer ROB_LEGACY_HALT_PAYLOAD = 1,\n    parameter integer ROB_RETURN_VALUE_ENABLE = 1,')
    text=once(text,'.LEGACY_HALT_PAYLOAD(ROB_LEGACY_HALT_PAYLOAD)',
        '.LEGACY_HALT_PAYLOAD(ROB_LEGACY_HALT_PAYLOAD), .RETURN_VALUE_ENABLE(ROB_RETURN_VALUE_ENABLE)')
    changes[name]=text
    name='rtl/backend/rv32_rob.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'parameter integer LEGACY_HALT_PAYLOAD = 1,',
        '''parameter integer LEGACY_HALT_PAYLOAD = 1,
    // In light mode the caller may omit this unconnected diagnostic value.
    // LSQ store payload and the MMIO side effect do not use this owner.
    parameter integer RETURN_VALUE_ENABLE = 1,''')
    old='''        rv32_rob_owned_field #(.WIDTH(31+1)) store_data_mem_owner (
            .clk_i(clk_i),.write_i(store_data_mem_write_enable[storage_row]),
            .data_i(store_data_mem_write_data[storage_row]),.data_o(store_data_mem[storage_row]));'''
    text=once(text,old,'''        if(LIGHT_RETIRE_PAYLOAD==0 || RETURN_VALUE_ENABLE!=0) begin:g_full_store_data
'''+old+'''
        end else begin:g_unobserved_store_data
            assign store_data_mem[storage_row]=32'b0;
        end''')
    text=once(text,'''(((MMIO_PREDECODE==0) ? 2*32+4 : 32) + ((LEGACY_HALT_PAYLOAD!=0)?32:0)));''',
        '''(((MMIO_PREDECODE==0) ? 32+4 : 0) + ((RETURN_VALUE_ENABLE!=0)?32:0) +
         ((LEGACY_HALT_PAYLOAD!=0)?32:0)));''')
    new=f'''    generate for(genvar packet_row=0;packet_row<ROB_ENTRIES;packet_row=packet_row+1) begin:g_commit_packet
        if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full
            assign commit_row_packet[packet_row]={pack(FULL,'packet_row')};
        end else begin:g_light
{generate_layout('            ','packet_row')}
        end
    end endgenerate'''
    text=replace_between(text,'    generate for(genvar packet_row=0;',
        '\n\n    wire [COMMIT_READ_WIDTH-1:0] bank_packet',new)
    new=f'''            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_packet
                assign {unpack(FULL,'read_lane')}=head_packet[read_lane];
            end else begin:g_light_packet
                assign head_pc[read_lane]=32'b0;
                assign head_inst[read_lane]=32'b0;
{generate_layout('                ','read_lane',output=True)}
            end'''
    text=replace_between(text,'            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_packet',
        '\n        end\n    endgenerate\n\n    localparam integer ALLOC_PACKET_WIDTH',new)
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
    record['enabled_profile']=dict(pm['enabled_profile'],RETURN_VALUE_ENABLE=0,
        commit_packet_bits=33,commit_selector_words=3,unused_rob_payload_bits_removed=5248)
    record['implemented_changes']=list(pm['implemented_changes'])+[
        'Course caller explicitly omits its unconnected internal return_value diagnostic; actual AXI MMIO payload remains LSQ-owned.'
    ]
    record['tests_started']=False
    record['material_gain_evidence']=dict(pm['material_gain_evidence'],
        unused_ROB_payload_bits_removed_at_ROB32=5248,additional_removed_store_data_bits=1024)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_PROJECTION_ONLY_NOT_FULL_CORE_EQUIVALENCE',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=list(changes),new_state_bits=0,added_pipeline_cycles=0,
        clocked_blocks_text_equal=True,tests_started=False,adopted=False,
        additional_unused_ROB_store_data_bits_removed=1024,
        changed_internal_output='cpu_core.return_value becomes zero in the explicit course light mode; it is unconnected in student_top.',
        preserved_observation_ports=['AXI read/write address/data/strobe/handshakes','debug_instret','debug_core_cycles','debug_error'],
        source_projection=[
            'student_top has no return_value port or connection; cpu_core only forwards backend return_value to that unused output.',
            'backend only forwards ROB return_value; ROB uses it only as an output register, not as a halt/commit/recovery predicate.',
            'ROB store_data_mem feeds the ignored commit/store payload outputs and ignored return_value; the store terminal predicate uses retained mmio_word_mem.',
            'Actual store bytes remain in LSQ data_mem. cpu_core dreq_payload_in is directly assembled from LSQ dcache_req_wdata, then the original MMIO bypass routes it to the external memory request.',
            'No LSQ data/update/request, ALU store operand, MMIO address/mask detection, store admission/ack or halted timing is changed.',
            'RETURN_VALUE_ENABLE defaults1 in core/backend/ROB. Full LIGHT_RETIRE_PAYLOAD=0 mode always retains the original store-data owner.',
            'All eight light layout combinations have matching pack/unpack and constant replacements; the current profile uses the33bit authority/mapping packet.',
            'This is course-top observational projection, not identical cpu_core diagnostic behavior or a whole-core formal proof.'
        ])
    write(BASE/'A9_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','additional_unused_ROB_store_data_bits_removed','tests_started')})


if __name__=='__main__':main()
