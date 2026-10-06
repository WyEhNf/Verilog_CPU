"""Prepare a source-only ER1 candidate with compact, optional ROB packets."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A4R2_light_retire_payload'
TARGET = BASE / 'A5_narrow_rob_packets'
COMMON = ['valid', 'ready', 'store', 'halt', 'error', 'store_wait',
          'store_sent', 'generation', 'rd_we', 'rd']
FULL = COMMON + ['pc', 'inst', 'value', 'store_addr', 'store_mask',
                 'store_data', 'old_phys', 'new_phys']
LIGHT_FALLBACK = COMMON + ['value', 'store_addr', 'store_mask',
                          'store_data', 'old_phys', 'new_phys']
LIGHT_MMIO = COMMON + ['value', 'store_data', 'old_phys', 'new_phys']


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def replace_between(text, start, end, new):
    assert text.count(start) == 1, start
    first = text.index(start)
    last = text.index(end, first)
    return text[:first] + new + text[last:]


def pack(fields, index):
    return '{' + ', '.join(f'{field}_mem[{index}]' for field in fields) + '}'


def unpack(fields, index):
    return '{' + ', '.join(f'head_{field}[{index}]' for field in fields) + '}'


def main():
    assert not TARGET.exists(), TARGET
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    name = 'rtl/backend/rv32_rob.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original,
                '''localparam integer COMMIT_READ_WIDTH = 8 + GENERATION_WIDTH + 5 +
        5*32 + 4 + 2*PHYS_ADDR_WIDTH;''',
                '''// Match the enabled field owners instead of routing constant trace words.
    localparam integer COMMIT_READ_WIDTH = 8 + GENERATION_WIDTH + 5 +
        2*PHYS_ADDR_WIDTH + ((LIGHT_RETIRE_PAYLOAD==0) ? 5*32+4 :
        ((MMIO_PREDECODE==0) ? 3*32+4 : 2*32));''')
    anchor = '    wire [COMMIT_READ_WIDTH-1:0] bank_packet [0:BE_WIDTH-1];'
    row_packet = f'''    wire [COMMIT_READ_WIDTH-1:0] commit_row_packet [0:ROB_ENTRIES-1];
    generate for(genvar packet_row=0;packet_row<ROB_ENTRIES;packet_row=packet_row+1) begin:g_commit_packet
        if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full
            assign commit_row_packet[packet_row]={pack(FULL, 'packet_row')};
        end else if(MMIO_PREDECODE==0) begin:g_mmio_fallback
            assign commit_row_packet[packet_row]={pack(LIGHT_FALLBACK, 'packet_row')};
        end else begin:g_light
            assign commit_row_packet[packet_row]={pack(LIGHT_MMIO, 'packet_row')};
        end
    end endgenerate

'''
    text = once(text, anchor, row_packet + anchor)
    # Check original three pack sites against the same ordered field list.
    expected_indices = ['bank_row*BE_WIDTH+commit_bank', 'row', 'row_index']
    for index in expected_indices:
        fields = re.findall(r'(\w+)_mem\[' + re.escape(index) + r'\]', original)
        assert any(fields[i:i+len(FULL)] == FULL for i in range(len(fields))), index
    text = replace_between(text,
        '                    assign row_packets[bank_row*COMMIT_READ_WIDTH +: COMMIT_READ_WIDTH]={',
        '\n                end\n                // PRIORITY=0',
        '                    assign row_packets[bank_row*COMMIT_READ_WIDTH +: COMMIT_READ_WIDTH]=\n'
        '                        commit_row_packet[bank_row*BE_WIDTH+commit_bank];')
    old = '''{valid_mem[row], ready_mem[row], store_mem[row], halt_mem[row],
                             error_mem[row], store_wait_mem[row], store_sent_mem[row],
                             generation_mem[row], rd_we_mem[row], rd_mem[row], pc_mem[row],
                             inst_mem[row], value_mem[row], store_addr_mem[row],
                             store_mask_mem[row], store_data_mem[row], old_phys_mem[row],
                             new_phys_mem[row]}'''
    text = once(text, old, 'commit_row_packet[row]')
    text = replace_between(text,
        '                assign head_packet[read_lane] =\n                    {valid_mem[row_index]',
        '\n            end\n            assign {head_valid',
        '                assign head_packet[read_lane] = commit_row_packet[row_index];')
    start = '            assign {head_valid[read_lane]'
    end = '\n        end\n    endgenerate\n\n    localparam integer ALLOC_PACKET_WIDTH'
    output = f'''            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_packet
                assign {unpack(FULL, 'read_lane')}=head_packet[read_lane];
            end else begin:g_light_packet
                assign head_pc[read_lane]=32'b0;
                assign head_inst[read_lane]=32'b0;
                if(MMIO_PREDECODE==0) begin:g_mmio_fallback
                    assign {unpack(LIGHT_FALLBACK, 'read_lane')}=head_packet[read_lane];
                end else begin:g_mmio_predecoded
                    assign head_store_addr[read_lane]=32'b0;
                    assign head_store_mask[read_lane]=4'b0;
                    assign {unpack(LIGHT_MMIO, 'read_lane')}=head_packet[read_lane];
                end
            end'''
    text = replace_between(text, start, end, output)
    text = once(text,
        '''localparam integer ALLOC_DATA_WIDTH=ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH+
        ((CHECKPOINT_IMPL==0)?CHECKPOINT_WIDTH:0);''',
        '''localparam integer ALLOC_DATA_WIDTH=ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH+
        ((CHECKPOINT_IMPL==0)?CHECKPOINT_WIDTH:0)-((LIGHT_RETIRE_PAYLOAD!=0)?64:0);''')
    text = once(text,
        '''if(CHECKPOINT_IMPL==0) begin:g_with_checkpoint
                            assign active_payload=full_payload;
                        end else begin:g_without_checkpoint
                            assign active_payload=full_payload[CHECKPOINT_WIDTH +: ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH];
                        end''',
        '''if(LIGHT_RETIRE_PAYLOAD!=0) begin:g_light_payload
                            if(CHECKPOINT_IMPL==0) begin:g_with_checkpoint
                                assign active_payload={full_payload[ALLOC_PACKET_WIDTH-1 -: 4],
                                    full_payload[0 +: CHECKPOINT_WIDTH+6+2*PHYS_ADDR_WIDTH]};
                            end else begin:g_without_checkpoint
                                assign active_payload={full_payload[ALLOC_PACKET_WIDTH-1 -: 4],
                                    full_payload[CHECKPOINT_WIDTH +: 6+2*PHYS_ADDR_WIDTH]};
                            end
                        end else if(CHECKPOINT_IMPL==0) begin:g_with_checkpoint
                            assign active_payload=full_payload;
                        end else begin:g_without_checkpoint
                            assign active_payload=full_payload[CHECKPOINT_WIDTH +: ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH];
                        end''')
    text = once(text,
        '''if(CHECKPOINT_IMPL==0) begin:g_full_result
                    assign bank_alloc_packet[alloc_bank]=packets[1];
                end else begin:g_compact_result
                    assign bank_alloc_packet[alloc_bank]={packets[1],{CHECKPOINT_WIDTH{1'b0}}};
                end''',
        '''if(LIGHT_RETIRE_PAYLOAD!=0) begin:g_light_result
                    // Reinsert constant trace slots at the original offsets. All
                    // allocation writes and priority still see the same full packet.
                    if(CHECKPOINT_IMPL==0) begin:g_full_result
                        assign bank_alloc_packet[alloc_bank]={packets[1][ALLOC_DATA_WIDTH-1 -: 4],
                            64'b0,packets[1][0 +: ALLOC_DATA_WIDTH-4]};
                    end else begin:g_compact_result
                        assign bank_alloc_packet[alloc_bank]={packets[1][ALLOC_DATA_WIDTH-1 -: 4],
                            64'b0,packets[1][0 +: ALLOC_DATA_WIDTH-4],{CHECKPOINT_WIDTH{1'b0}}};
                    end
                end else if(CHECKPOINT_IMPL==0) begin:g_full_result
                    assign bank_alloc_packet[alloc_bank]=packets[1];
                end else begin:g_compact_result
                    assign bank_alloc_packet[alloc_bank]={packets[1],{CHECKPOINT_WIDTH{1'b0}}};
                end''')
    assert blocks(original) == blocks(text)
    for name in parent['source_sha256']:
        dest = TARGET / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dest)
    (TARGET / 'rtl/backend/rv32_rob.v').write_text(text, encoding='utf-8')
    record = dict(
        status='PREPARED_UNTESTED_NOT_ADOPTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        measured_reference_run='F:/CPU2026CourseRuns/architecture_ER1_20261005',
        reference_ipc_run='F:/CPU2026CourseRuns/ER1_native_identifier_compat_20261005',
        framework_commit=parent['framework_commit'], testcases_commit=parent['testcases_commit'],
        latency=10, measurement_host='Windows native only',
        parameter_overrides=parent['parameter_overrides'],
        source_sha256={n: sha(TARGET / n) for n in parent['source_sha256']},
        changed_from_parent_files=['rtl/backend/rv32_rob.v'],
        ordinary_integer_pipeline_depth=10,
        enabled_profile=dict(ROB_ENTRIES=32,PHYS_REGS=56,RS_ENTRIES=8,DCACHE_LINES=512,
            rob_generation_bits=8,phys_addr_bits=6,commit_packet_bits=97,
            allocation_active_packet_bits=22,commit_selector_words=7,allocation_selector_words=2),
        implemented_changes=[
            'Inherited ER1 parallel LSQ selection and native identifier compatibility.',
            'Ready-load allocation through existing signed-12-bit allocation address adders.',
            'Existing D-cache hit response bypass enabled.',
            'ROB32/PRF56/RS8/DCACHE512 with four-wide issue retained.',
            'Optional unused ROB trace/address/mask field owners removed; authority/terminal data retained.',
            'Compact retirement and allocation selection packets with default/fallback full interfaces retained.'
        ],
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None,
        target=dict(minimum_fmax_mhz=300,ipc=1.1,total_area_um2=36000),
        source_review='Source inspection and preparation only; not a full-core proof.',
        preparation_script_sha256=sha(Path(__file__)))
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_REVIEW_ONLY_NOT_FULL_CORE_PROOF',candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'),parent_sha256=sha(PARENT / 'candidate.json'),
        changed_files=record['changed_from_parent_files'],new_state_bits=0,added_pipeline_cycles=0,
        rob_clocked_blocks_text_equal=len(blocks(text)),
        full_pack_fields=FULL,light_fallback_pack_fields=LIGHT_FALLBACK,
        light_mmio_pack_fields=LIGHT_MMIO,
        argument=[
            'All three original read sites use the same field order; bank selection/OR mask/rotation/indexing remain.',
            'Default mode pack/unpack is identical. Light mode routes precisely the existing enabled field owners.',
            'Light MMIO fallback retains address/mask for terminal decode; predecoded mode produces the same A4 constants.',
            'Allocation removes only the two constant trace slots before the original grants/word AND/OR reduction.',
            'Trace slots are reinserted at their original offsets after selection; allocation writes are unchanged.',
            'Deletion/reinsertion commutes with each bitwise AND/OR, including no grants or multiple grants.',
            'Neither state, authority, recovery qualification, commit prefix, terminal value nor clock edge changes.',
            'Mapped area/timing and full-core behavior remain unmeasured.'
        ],tests_started=False,adopted=False)
    write(BASE / 'A5_source_review.json', proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','new_state_bits','tests_started')})


if __name__ == '__main__':
    main()
