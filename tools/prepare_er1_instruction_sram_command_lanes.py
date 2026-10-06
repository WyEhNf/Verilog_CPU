"""Remove hit qualification from L0 SRAM reads and bound macro pin fanout."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A37_mdu_local_payload_owners'
TARGET=BASE/'A38_instruction_sram_command_lanes'
MEASURED=Path('F:/CPU2026CourseRuns/ER1_A36_tier3_20261005')


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    critical=read(MEASURED/'result/synth/opt/critical_paths.json')['checks'][0]
    assert '.g_instruction_line_filter.lines.g_sram_lines.g_bank[0].data.lane_0/addr_in[0]' in critical['endpoint']
    measured=read(MEASURED/'result/result.json')
    assert measured['fmax_mhz']==297.2423802612482
    name='rtl/cache/rv32_icache_nonblocking.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'''            wire [INDEX_WIDTH-1:0] read_index=bank_hit?
                if_req_pc_i[4 +: INDEX_WIDTH]:fast_pc[4 +: INDEX_WIDTH];
            wire [SRAM_ADDR_WIDTH-1:0] address=bank_fill?
                SRAM_ADDR_WIDTH'(primary_resp_line_addr_i[4 +: INDEX_WIDTH] >> SRAM_BANK_WIDTH):
                SRAM_ADDR_WIDTH'(read_index >> SRAM_BANK_WIDTH);
            sram_fakeram #(.DEPTH(SRAM_DEPTH),.WIDTH(128),.WRITE_GRANULARITY(16)) data (
                .clk(clk_i),.en(!reset_i && (bank_fill || bank_hit || bank_hold)),
                .we(bank_fill),.wmask(8'hff),.addr(address),
                .wdata(primary_resp_line_data_i),.rdata(bank_data[bank*128 +: 128]));''','''            // Hold chooses the saved PC; otherwise an offered request PC is
            // safe before its tag/hit acceptance. Extra speculative reads do
            // not publish a response: fast_identity/valid still use accept_hit.
            wire hold_read=fast_live && !fast_slot_free;
            wire offered_read=if_req_valid_i && fast_slot_free &&
                if_req_pc_i[4 +: SRAM_BANK_WIDTH]==BANK;
            wire [INDEX_WIDTH-1:0] read_index=hold_read?
                fast_pc[4 +: INDEX_WIDTH]:if_req_pc_i[4 +: INDEX_WIDTH];
            wire [SRAM_ADDR_WIDTH-1:0] address=bank_fill?
                SRAM_ADDR_WIDTH'(primary_resp_line_addr_i[4 +: INDEX_WIDTH] >> SRAM_BANK_WIDTH):
                SRAM_ADDR_WIDTH'(read_index >> SRAM_BANK_WIDTH);
            localparam integer COMMAND_WIDTH=SRAM_ADDR_WIDTH+2;
            wire [8*COMMAND_WIDTH-1:0] commands;
            rv32_frequency_control_tree #(.WIDTH(COMMAND_WIDTH),.LEAVES(8)) command_tree (
                .signal_i({!reset_i && (bank_fill || offered_read || bank_hold),bank_fill,address}),
                .views_o(commands));
            // Same eight physical4x16 macros per bank as the former128-bit
            // wrapper expansion; each priced command leaf drives one macro.
            for(genvar data_lane=0;data_lane<8;data_lane=data_lane+1) begin:g_data_lane
                wire enable,write;
                wire [SRAM_ADDR_WIDTH-1:0] lane_address;
                assign {enable,write,lane_address}=commands[data_lane*COMMAND_WIDTH +: COMMAND_WIDTH];
                sram_fakeram #(.DEPTH(SRAM_DEPTH),.WIDTH(16),.WRITE_GRANULARITY(16)) data (
                    .clk(clk_i),.en(enable),.we(write),.wmask(1'b1),.addr(lane_address),
                    .wdata(primary_resp_line_data_i[data_lane*16 +: 16]),
                    .rdata(bank_data[bank*128+data_lane*16 +: 16]));
            end''')
    start=original.index('            wire [INDEX_WIDTH-1:0] read_index=bank_hit?')
    end=original.index('            assign response_banks[bank]',start)
    new_start=text.index('            // Hold chooses the saved PC;')
    new_end=text.index('            assign response_banks[bank]',new_start)
    assert text[:new_start]==original[:start] and text[new_end:]==original[end:]
    for n in parent['source_sha256']:
        dest=TARGET/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/n,dest)
    (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['enabled_profile']=dict(parent['enabled_profile'],instruction_filter_offered_read=True,
        instruction_filter_macro_command_lanes=8,instruction_filter_added_ff_bits=0,
        instruction_filter_added_sram_bits=0,instruction_filter_added_pipeline_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Use held-PC or offered-PC L0 SRAM address without waiting for tag/acceptance; preread only the offered bank while response slot is free. Preserve accept_hit as sole response publisher. Split each128-bit wrapper into eight16-bit macros with individually priced command leaves; identical total macros/area/read latency.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        a36_measured_critical_path_endpoint=critical['endpoint'],
        a36_measured_critical_paths_sha256=sha(MEASURED/'result/synth/opt/critical_paths.json'),
        a36_instruction_sram_address_driver_load_ff=40.0,
        a36_instruction_sram_address_driver_delay_ns=.479,
        instruction_filter_hit_acceptance_removed_from_read_address=True,
        instruction_filter_new_extra_state_bits=0,instruction_filter_macro_count_changed=False,
        instruction_filter_command_actual_timing_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_L0_OFFERED_READ_AND_ONE_MACRO_COMMAND_LEAF_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=[name],
        added_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,original_clocked_control_text_exact=True,
        macro_configuration_before='four banks x depth4 width128 gran16 ->32 physical4x16',
        macro_configuration_after='four banks x eight depth4 width16 gran16 ->32 physical4x16',
        tests_started=False,adopted=False,
        source_arguments=[
            'A36 new worst path ends at instruction L0 bank0 SRAM addr[0], arrival3.263ns; its last NAND2 driver has40fF load and.479ns delay. Unlike the old A21 MDU path, this is current-source timing evidence.',
            'An accepted hit implies request offered, fast_slot_free, no same-bank fill conflict, and matching request bank. Its original held/read address chooses request PC. New offered read selects that same request PC and enables that bank before full tag/hit qualification, so accepted hit SRAM contents are identical.',
            'A held live response implies !fast_slot_free and the selected saved bank. Both versions read saved fast_pc and reread each stalled edge. Offered read is disabled while held; fill still has highest write/address priority.',
            'Additional reads when an offered request is a miss, stale epoch, blocked by the primary cache, or a same-bank fill conflict do not change data/tag/valid state or create a response. accept_hit still exclusively writes fast PC/epoch and controls fast_valid; any same-bank fill makes write win in every lane.',
            'The primary filter fill/read conflicts, full tags, metadata capture, pending miss, SRAM Q invalidation on idle/write, output selection, fast response lifetime/handshake and all clocked source outside this SRAM command block are exact parent bytes.',
            'Each original width128 gran16 FakeRAM is eight independent16-bit lane macros with common en/we/address. New wrappers instantiate those same eight lanes explicitly and preserve every enable/write/read edge and little-endian16-bit slice. Macro count32, total2048 SRAM bits and official area85.996352um2 remain unchanged.',
            'Priced command_tree leaves distribute enable/write/address to one5fF macro pin each, rather than one mapped address gate directly driving eight5fF pins. Buffer/extra read control logic adds mapped area, but no FF, memory capacity, register boundary or latency.',
            'Current filter remains1edge warm-hit latency. Extra speculative read activity is an energy cost; power is not a target metric. Actual frequency/area and source correctness remain unmeasured.',
            'No HDL build, lint, simulation, synthesis, STA, CPU/perf or unit tests. Later meaningful coverage includes repeated/held hits, offered miss/backpressure, bank write conflict, epoch redirect, errors and physical macro accounting.'
        ])
    write(BASE/'A38_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','added_sram_bits','added_pipeline_edges','tests_started')})


if __name__=='__main__':main()
