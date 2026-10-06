"""Keep terminal MMIO data but omit unused ordinary ROB result payload."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks
from prepare_er1_narrow_rob_packets import COMMON, FULL, LIGHT_FALLBACK, LIGHT_MMIO, pack, unpack

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A6_ready_load_no_agu'
TARGET=BASE/'A7_mmio_retire_value'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def replace_between(text,start,end,new):
    assert text.count(start)==1,start
    first=text.index(start);last=text.index(end,first)
    return text[:first]+new+text[last:]


def main():
    assert not TARGET.exists(),TARGET
    pm=read(PARENT/'candidate.json')
    for name,digest in pm['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_backend_joint.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'parameter integer LIGHT_RETIRE_PAYLOAD = 0,',
              'parameter integer LIGHT_RETIRE_PAYLOAD = 0,\n    parameter integer ROB_LEGACY_HALT_PAYLOAD = 1,')
    text=once(text,'.LIGHT_RETIRE_PAYLOAD(LIGHT_RETIRE_PAYLOAD)',
              '.LIGHT_RETIRE_PAYLOAD(LIGHT_RETIRE_PAYLOAD), .LEGACY_HALT_PAYLOAD(ROB_LEGACY_HALT_PAYLOAD)')
    changes[name]=text
    name='rtl/cpu_core.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'.LIGHT_RETIRE_PAYLOAD(LIGHT_RETIRE_PAYLOAD)',
              '.LIGHT_RETIRE_PAYLOAD(LIGHT_RETIRE_PAYLOAD), .ROB_LEGACY_HALT_PAYLOAD(LEGACY_SENTINEL_HALT)')
    changes[name]=text
    name='rtl/backend/rv32_rob.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'parameter integer LIGHT_RETIRE_PAYLOAD = 0,',
              '''parameter integer LIGHT_RETIRE_PAYLOAD = 0,
    // Set to zero only when the caller cannot allocate a legacy HALT.
    // MMIO terminal data remains in store_data_mem in every mode.
    parameter integer LEGACY_HALT_PAYLOAD = 1,''')
    old='''        rv32_rob_owned_field #(.WIDTH(31+1)) value_mem_owner (
            .clk_i(clk_i),.write_i(value_mem_write_enable[storage_row]),
            .data_i(value_mem_write_data[storage_row]),.data_o(value_mem[storage_row]));'''
    text=once(text,old,'''        if(LIGHT_RETIRE_PAYLOAD==0 || LEGACY_HALT_PAYLOAD!=0) begin:g_full_value
'''+old+'''
        end else begin:g_unobserved_value
            assign value_mem[storage_row]=32'b0;
        end''')
    text=once(text,'''2*PHYS_ADDR_WIDTH + ((LIGHT_RETIRE_PAYLOAD==0) ? 5*32+4 :
        ((MMIO_PREDECODE==0) ? 3*32+4 : 2*32));''',
        '''2*PHYS_ADDR_WIDTH + ((LIGHT_RETIRE_PAYLOAD==0) ? 5*32+4 :
        (((MMIO_PREDECODE==0) ? 2*32+4 : 32) + ((LEGACY_HALT_PAYLOAD!=0)?32:0)));''')
    fallback=[f for f in LIGHT_FALLBACK if f!='value']
    mmio=[f for f in LIGHT_MMIO if f!='value']
    new=f'''    generate for(genvar packet_row=0;packet_row<ROB_ENTRIES;packet_row=packet_row+1) begin:g_commit_packet
        if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full
            assign commit_row_packet[packet_row]={pack(FULL,'packet_row')};
        end else if(MMIO_PREDECODE==0) begin:g_mmio_fallback
            if(LEGACY_HALT_PAYLOAD!=0) begin:g_with_halt
                assign commit_row_packet[packet_row]={pack(LIGHT_FALLBACK,'packet_row')};
            end else begin:g_without_halt
                assign commit_row_packet[packet_row]={pack(fallback,'packet_row')};
            end
        end else begin:g_light
            if(LEGACY_HALT_PAYLOAD!=0) begin:g_with_halt
                assign commit_row_packet[packet_row]={pack(LIGHT_MMIO,'packet_row')};
            end else begin:g_without_halt
                assign commit_row_packet[packet_row]={pack(mmio,'packet_row')};
            end
        end
    end endgenerate'''
    text=replace_between(text,'    generate for(genvar packet_row=0;',
                         '\n\n    wire [COMMIT_READ_WIDTH-1:0] bank_packet',new)
    new=f'''            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_packet
                assign {unpack(FULL,'read_lane')}=head_packet[read_lane];
            end else begin:g_light_packet
                assign head_pc[read_lane]=32'b0;
                assign head_inst[read_lane]=32'b0;
                if(MMIO_PREDECODE==0) begin:g_mmio_fallback
                    if(LEGACY_HALT_PAYLOAD!=0) begin:g_with_halt
                        assign {unpack(LIGHT_FALLBACK,'read_lane')}=head_packet[read_lane];
                    end else begin:g_without_halt
                        assign head_value[read_lane]=32'b0;
                        assign {unpack(fallback,'read_lane')}=head_packet[read_lane];
                    end
                end else begin:g_mmio_predecoded
                    assign head_store_addr[read_lane]=32'b0;
                    assign head_store_mask[read_lane]=4'b0;
                    if(LEGACY_HALT_PAYLOAD!=0) begin:g_with_halt
                        assign {unpack(LIGHT_MMIO,'read_lane')}=head_packet[read_lane];
                    end else begin:g_without_halt
                        assign head_value[read_lane]=32'b0;
                        assign {unpack(mmio,'read_lane')}=head_packet[read_lane];
                    end
                end
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
    record['enabled_profile']=dict(pm['enabled_profile'],commit_packet_bits=65,
        commit_selector_words=5,LEGACY_HALT_PAYLOAD=0,unused_rob_payload_bits_removed=4224)
    record['implemented_changes']=list(pm['implemented_changes'])+[
        'Omit ordinary ROB result storage in light mode when legacy HALT is disabled; keep MMIO terminal data.'
    ]
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_REVIEW_ONLY_NOT_FULL_CORE_PROOF',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=list(changes),new_state_bits=0,added_pipeline_cycles=0,
        clocked_blocks_text_equal=True,tests_started=False,adopted=False,
        ordinary_value_bits_removed=1024,total_unused_payload_bits_removed=4224,
        reasoning=[
            'student_top explicitly passes LEGACY_SENTINEL_HALT=0; rv32im_decoder emits OP_HALT only in the guarded legacy-sentinel block.',
            'cpu_core is_halt_trace is solely OP_HALT; therefore this course caller cannot allocate legacy HALT.',
            'cpu_core supplies LEGACY_SENTINEL_HALT to the new backend/ROB contract; enabling the sentinel automatically retains HALT return values.',
            'ROB value_mem reaches only unconnected commit_value and legacy HALT return. Ordinary architectural writes use the PRF/CDB path, which is unchanged.',
            'MMIO return_value still reads head_store_data from the retained original store_data_mem owner; exception and halt timing remain unchanged.',
            'Full LIGHT_RETIRE_PAYLOAD=0 mode and the standalone default retain all result payloads.',
            'Every enabled pack has a matching unpack and width. MMIO_PREDECODE=0 retains address/mask fallback.',
            'No clocked text, authority, full generation check or recovery state changes. Final whole-core verification remains necessary.'
        ])
    write(BASE/'A7_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','ordinary_value_bits_removed','tests_started')})


if __name__=='__main__':main()
