"""Select address qualification flags with the exact PRF store-address events."""
from datetime import datetime,timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read,sha,write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A79_ready_ram_store_complete'
TARGET = BASE/'A80_fast_store_address_predecode'
REVIEW = BASE/'A80_source_review.json'


def once(text,old,new):
    assert text.count(old) == 1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'f7d8733c830c1e3a6e488034a4c6fc9dc52c09d0bc55bd7c0d172e1a52a02c0a'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest,name
    changes = {}
    name = 'rtl/rv32_physical_register_file.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original,'    parameter integer STORE_ADDRESS_READ = 0,',
        '''    parameter integer STORE_ADDRESS_READ = 0,
    // Optional ram/half/word alignment flags computed before the same
    // stored/write-through address event selector. No state or edge added.
    parameter integer STORE_ADDRESS_FLAGS = 0,''')
    text = once(text,'    output wire [BE_WIDTH*32-1:0]       store_address_o',
        '''    output wire [BE_WIDTH*32-1:0]       store_address_o,
    output wire [BE_WIDTH*3-1:0]        store_address_flags_o''')
    marker = '''                    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(BE_WIDTH+1),.PRIORITY(1)) address_selector (
                        .events_i(address_events),.values_i(address_values),.write_o(),
                        .value_o(store_address_o[(rp/2)*32 +: 32]));'''
    text = once(text,marker,marker+'''
                    if(STORE_ADDRESS_FLAGS!=0) begin:g_address_flags
                        wire [(BE_WIDTH+1)*3-1:0] flag_values;
                        for(genvar flag_lane=0;flag_lane<BE_WIDTH+1;flag_lane=flag_lane+1) begin:g_candidate
                            wire [31:0] candidate_address=address_values[flag_lane*32 +: 32];
                            // bit0: ordinary RAM; bit1: half alignment;
                            // bit2: word alignment. All wrap/carry is already
                            // included by the exact original address adder.
                            assign flag_values[flag_lane*3 +: 3]={
                                candidate_address[1:0]==2'b00,
                                !candidate_address[0],candidate_address[31:28]==4'b0000};
                        end
                        rv32_frequency_event_select #(.WIDTH(3),.EVENTS(BE_WIDTH+1),.PRIORITY(1)) flags_selector (
                            .events_i(address_events),.values_i(flag_values),.write_o(),
                            .value_o(store_address_flags_o[(rp/2)*3 +: 3]));
                    end else begin:g_no_address_flags
                        assign store_address_flags_o[(rp/2)*3 +: 3]=0;
                    end''')
    text = once(text,'''                end else begin:g_disabled
                    assign store_address_o[(rp/2)*32 +: 32]=0;''',
        '''                end else begin:g_disabled
                    assign store_address_o[(rp/2)*32 +: 32]=0;
                    assign store_address_flags_o[(rp/2)*3 +: 3]=0;''')
    text = once(text,'    assign store_address_o=0;',
        '    assign store_address_o=0;\n    assign store_address_flags_o=0;')
    # Original state, reads/readiness, write-through priority, and every
    # address payload/adder/extraction remain unchanged. Extra flags have
    # their own <=3bit masked-OR selector driven by identical events.
    for marker in ['assign address_events[0]=!bypass_write;',
                   'assign address_events[address_lane+1]=bypass_match[address_lane];',
                   'read_ready_o[rp]=(address==0) || ready_tree[1] || bypass_write;',
                   'wire legal=address!=0 && address<PHYS_REGS;']:
        assert marker in text,marker
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        old = '    parameter integer FAST_STORE_COMPLETE = '+str(default)+','
        text = once(original,old,old+'\n    parameter integer FAST_STORE_ADDRESS_PREDECODE = '+str(default)+',')
        if '/backend/' in name:
            text = once(text,'    wire [BE_WIDTH*32-1:0] prf_store_address;',
                '    wire [BE_WIDTH*32-1:0] prf_store_address;\n    wire [BE_WIDTH*3-1:0] prf_store_address_flags;')
            text = once(text,'.STORE_ADDRESS_READ(PARALLEL_STORE_ADDRESS)',
                '.STORE_ADDRESS_READ(PARALLEL_STORE_ADDRESS), .STORE_ADDRESS_FLAGS((FAST_STORE_ADDRESS_PREDECODE!=0) && FAST_STORE_COMPLETE_ACTIVE && PARALLEL_STORE_ADDRESS)')
            text = once(text,'.store_address_o(prf_store_address)',
                '.store_address_o(prf_store_address), .store_address_flags_o(prf_store_address_flags)')
            text = once(text,'            wire ordinary_store=(op==`RV32IM_OP_SB && size==2\'d0) ||',
                '''            wire [2:0] address_flags=((FAST_STORE_ADDRESS_PREDECODE!=0) && PARALLEL_STORE_ADDRESS) ?
                prf_store_address_flags[ready_store_lane*3 +: 3] :
                {address[1:0]==2'b00,!address[0],address[31:28]==4'b0000};
            wire ordinary_store=(op==`RV32IM_OP_SB && size==2'd0) ||''')
            text = once(text,"(op==`RV32IM_OP_SH && size==2'd1 && !address[0])", "(op==`RV32IM_OP_SH && size==2'd1 && address_flags[1])")
            text = once(text,"(op==`RV32IM_OP_SW && size==2'd2 && address[1:0]==2'b00)", "(op==`RV32IM_OP_SW && size==2'd2 && address_flags[2])")
            text = once(text,"                address[31:28]==4'b0000 && ordinary_store && canonical_immediate;",
                '                address_flags[0] && ordinary_store && canonical_immediate;')
        else:
            text = once(text,'.FAST_STORE_COMPLETE(FAST_STORE_COMPLETE)',
                '.FAST_STORE_COMPLETE(FAST_STORE_COMPLETE), .FAST_STORE_ADDRESS_PREDECODE(FAST_STORE_ADDRESS_PREDECODE)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_FAST_STORE_ADDRESS_PREDECODE_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],FAST_STORE_ADDRESS_PREDECODE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],FAST_STORE_ADDRESS_PREDECODE=1,
        fast_store_address_class_bits_per_lane=3,fast_store_address_class_new_ff_bits=0,
        fast_store_address_class_new_sram_bits=0,fast_store_address_class_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Compute ordinary-RAM and half/word alignment predicates for each exact existing PRF store-address candidate before its write-through address event selection. Carry only3bits with the identical stored fallback/highest-write-lane event priority. Enabled fast-store eligibility uses those flags, avoiding selected32bit address followed by legality compares. Actual address/data, fast publication/ROB lifetime and all state/handshake edges remain original. Unsupported/disabled parallel-address profiles compare the actual address as in A79.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        fast_store_address_class_before_write_through_selection=True,
        fast_store_address_predecode_limit='Targets an added A79 structural ready-control dependency, not an already measured A79/A80 slow path. Original fallback PRF-read plus adder and WB adders still remain; flags-selector/compare gates cost unknown. No extra IPC edge removal or measured area/Fmax claim.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'A79 newly gates fast-store admission with RAM upper-nibble and size/alignment qualification after its current authoritative allocation address selection. Move those predicates before the original stored/write-through candidate selector to remove that extra serial data-to-control dependency; no measured A79/A80 timing is claimed.',
            'Existing address_events[0]=!bypass_write, higher events=bypass_match[write_lane], and PRIORITY1 selector choose the highest matched legal physical write lane or exact original un-bypassed stored-tree fallback. This event set always has a winner. New3bit flags use the same event set and priority, so flags exactly equal RAM/half/word predicates of the selected32bit address for P0, legal/illegal physical rows, duplicate write tags and every wrap/carry/negative12 offset.',
            'Candidate address adders/payloads remain byte-identical; only extra combinational predicates/selectors are inserted. PRF read_data/read_ready, allocation/write state and priority do not consume the flags. No FF/SRAM/edge, source legality relaxation or write port is added.',
            'Backend consumes flags only when fast-store profile and original parallel address profile are active. Parameter0 or nonparallel address uses exact original A79 actual-address comparisons; inactive PRF branches drive flags0. Store opcode/size/canonical immediate, real LSQ alloc_fire and full ROB valid/row/8GEN checks are unchanged. Default standalone PRF callers may leave the extra output unconnected.',
            'Manual source/event-priority reasoning only; no HDL/lint/formal/simulation/synthesis/STA/unit test run. Future complete batch includes stored and WB address paths, both WB lanes/duplicate identities, P0/out-of-range IDs, positive/negative/wrapping offsets, crossing RAM boundary, byte/half/word alignment, flag0/1 and nonparallel/fast-inactive profiles at widths1/2/4. New gate area and cumulative IPC/Fmax/area remain unknown.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
