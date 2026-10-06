"""Remove WB data/classification from fast-store admission without D stalls."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A86_head_store_ack_bypass'
TARGET = BASE/'A87_saved_store_operands_parallel_admission'
REVIEW = BASE/'A87_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'a118f5381b22dcf0b10fdb2e22777a29e6532a8c43a4f7858a24ee67c4e0cacd'
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/rv32_physical_register_file.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer STORE_ADDRESS_FLAGS = 0,',
        '''    parameter integer STORE_ADDRESS_FLAGS = 0,
    // Private saved-operand qualification; never changes public read data.
    parameter integer STORE_SAVED_QUERY = 0,''')
    text = once(text, '    output wire [BE_WIDTH*3-1:0]        store_address_flags_o',
        '''    output wire [BE_WIDTH*3-1:0]        store_address_flags_o,
    output wire [2*BE_WIDTH-1:0]       read_stored_ready_o,
    output wire [2*BE_WIDTH-1:0]       read_bypass_pending_o,
    output wire [BE_WIDTH*3-1:0]       store_saved_flags_o''')
    marker = '''            rv32_frequency_control_tree #(.LEAVES(2)) bypass_choice_tree (
                .signal_i(bypass_write),.views_o(bypass_select));'''
    text = once(text, marker, marker+'''
            if(STORE_SAVED_QUERY!=0) begin:g_saved_operand_query
                assign read_stored_ready_o[rp]=(address==0) || ready_tree[1];
                assign read_bypass_pending_o[rp]=bypass_write;
            end else begin:g_no_saved_operand_query
                assign read_stored_ready_o[rp]=1'b0;
                assign read_bypass_pending_o[rp]=1'b0;
            end''')
    marker = '''                        .sum_o(address_values[0 +: 32]));'''
    text = once(text, marker, marker+'''
                    if(STORE_SAVED_QUERY!=0) begin:g_saved_address_flags
                        wire [31:0] saved_address=address_values[0 +: 32];
                        assign store_saved_flags_o[(rp/2)*3 +: 3]={
                            saved_address[1:0]==2'b00,!saved_address[0],
                            saved_address[31:28]==4'b0000};
                    end else begin:g_no_saved_address_flags
                        assign store_saved_flags_o[(rp/2)*3 +: 3]=0;
                    end''')
    marker = '''                end else begin:g_disabled
                    assign store_address_o[(rp/2)*32 +: 32]=0;
                    assign store_address_flags_o[(rp/2)*3 +: 3]=0;'''
    text = once(text, marker, marker+'\n                    assign store_saved_flags_o[(rp/2)*3 +: 3]=0;')
    marker = '    assign store_address_flags_o=0;'
    text = once(text, marker, marker+'''
    assign read_stored_ready_o=0;
    assign read_bypass_pending_o=0;
    assign store_saved_flags_o=0;''')
    # Public storage/read/write priorities are not altered by private queries.
    marker = '    generate if(LOCAL_VALUE_ROWS==0) begin:g_legacy_storage'
    assert text[text.index(marker):] == original[original.index(marker):]
    for marker in [
        'assign address_events[0]=!bypass_write;',
        'assign address_events[address_lane+1]=bypass_match[address_lane];',
        'read_ready_o[rp]=(address==0) || ready_tree[1] || bypass_write;',
        'wire legal=address!=0 && address<PHYS_REGS;',
        'assign bypass_match[wl]=legal && write_valid_i[wl] &&']:
        assert marker in text, marker
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer FAST_STORE_ADDRESS_PREDECODE = '+str(default)+','
        text = once(original, marker, marker+'\n    parameter integer FAST_STORE_SAVED_OPERANDS = '+str(default)+',')
        if '/backend/' in name:
            marker = '    wire [BE_WIDTH-1:0] ready_store_candidates,store_without_agu,rob_fast_store_valid;'
            text = once(text, marker, '''    localparam integer FAST_STORE_SAVED_ACTIVE=(FAST_STORE_SAVED_OPERANDS!=0) &&
        FAST_STORE_COMPLETE_ACTIVE && PARALLEL_STORE_ADDRESS;
'''+marker)
            marker = '    wire [BE_WIDTH*3-1:0] prf_store_address_flags;'
            text = once(text, marker, marker+'''
    wire [2*BE_WIDTH-1:0] prf_read_stored_ready,prf_read_bypass_pending;
    wire [BE_WIDTH*3-1:0] prf_store_saved_flags;''')
            text = once(text, '.STORE_ADDRESS_FLAGS((FAST_STORE_ADDRESS_PREDECODE!=0) && FAST_STORE_COMPLETE_ACTIVE && PARALLEL_STORE_ADDRESS)',
                '.STORE_ADDRESS_FLAGS((FAST_STORE_ADDRESS_PREDECODE!=0) && FAST_STORE_COMPLETE_ACTIVE && PARALLEL_STORE_ADDRESS), .STORE_SAVED_QUERY(FAST_STORE_SAVED_ACTIVE)')
            text = once(text, '.store_address_flags_o(prf_store_address_flags),',
                '''.store_address_flags_o(prf_store_address_flags),
        .read_stored_ready_o(prf_read_stored_ready), .read_bypass_pending_o(prf_read_bypass_pending),
        .store_saved_flags_o(prf_store_saved_flags),''')
            marker = '''            wire [2:0] address_flags=((FAST_STORE_ADDRESS_PREDECODE!=0) && PARALLEL_STORE_ADDRESS) ?'''
            text = once(text, marker, '''            wire [2:0] address_flags=(FAST_STORE_SAVED_ACTIVE!=0) ?
                prf_store_saved_flags[ready_store_lane*3 +: 3] :
                ((FAST_STORE_ADDRESS_PREDECODE!=0) && PARALLEL_STORE_ADDRESS) ?''')
            marker = '''            assign ready_store_candidates[ready_store_lane]=d_valid[ready_store_lane] &&'''
            text = once(text, marker, '''            // Matching WB uses the original RS execution fallback, even if
            // a stored value was already ready. No extra D hold is introduced.
            wire operands_qualified=(FAST_STORE_SAVED_ACTIVE!=0) ?
                (prf_read_stored_ready[2*ready_store_lane] &&
                 prf_read_stored_ready[2*ready_store_lane+1] &&
                 !prf_read_bypass_pending[2*ready_store_lane] &&
                 !prf_read_bypass_pending[2*ready_store_lane+1]) :
                (lsq_alloc_addr_valid[ready_store_lane] && lsq_alloc_data_valid[ready_store_lane]);
'''+marker)
            text = once(text, '                lsq_alloc_addr_valid[ready_store_lane] && lsq_alloc_data_valid[ready_store_lane] &&',
                '                operands_qualified &&')
            marker = '    reg [CREDIT_WIDTH-1:0] d_rs_demand,d_lsq_demand;'
            text = once(text, marker, '''    // At most one store skips RS. Compute both capacity cases before
    // its late qualification, instead of counting that bit then comparing.
    wire [BE_WIDTH-1:0] d_rs_base_need=d_valid & ~load_without_agu;
'''+marker+'\n    reg [CREDIT_WIDTH-1:0] d_rs_base_demand;')
            text = once(text, '        d_rs_demand=0;d_lsq_demand=0;',
                '        d_rs_demand=0;d_lsq_demand=0;d_rs_base_demand=0;')
            marker = '            d_rs_demand=d_rs_demand+d_rs_need[demand_lane];'
            text = once(text, marker, marker+'\n            d_rs_base_demand=d_rs_base_demand+d_rs_base_need[demand_lane];')
            marker = '    assign d_admit=(DISPATCH_ELASTIC==0) ||'
            text = once(text, marker, '''    wire d_rs_room_ordinary=(d_rs_base_demand<=rs_free_count);
    // Extend the original 16-bit free count before adding one: no wrap at
    // 16'hffff. F=1 implies base demand>=1, so no subtraction underflows.
    wire d_rs_room_with_fast=(d_rs_base_demand<=({1'b0,rs_free_count}+17'd1));
    wire d_rs_capacity_ok=(FAST_STORE_SAVED_ACTIVE!=0) ?
        (d_rs_room_ordinary || ((|store_without_agu) && d_rs_room_with_fast)) :
        (d_rs_demand<=rs_free_count);
'''+marker)
            text = once(text, '         (d_rs_demand<=rs_free_count) && (d_lsq_demand<=lsq_free_count));',
                '         d_rs_capacity_ok && (d_lsq_demand<=lsq_free_count));')
            start = '    reg [CREDIT_WIDTH-1:0] d_replace_rs_demand,d_replace_lsq_demand;'
            end = '    assign d_admit='
            original_credit = original[original.index(start):original.index(end)]
            assert text[text.index(start):text.index('    wire d_rs_room_ordinary=')] == original_credit
            # The actual allocator payload and source-value preparation remain
            # original; private queries only narrow the optional fast case.
            for start,end in [
                ('    genvar io_lane,link_word;','    // The same predicate that writes an authoritative LSQ address'),
                ('    // Rename and PRF form the operand/producer boundary.','    localparam integer PARALLEL_STORE_ADDRESS=')]:
                assert text[text.index(start):text.index(end)] == original[original.index(start):original.index(end)]
        else:
            text = once(text, '.FAST_STORE_ADDRESS_PREDECODE(FAST_STORE_ADDRESS_PREDECODE)',
                '.FAST_STORE_ADDRESS_PREDECODE(FAST_STORE_ADDRESS_PREDECODE), .FAST_STORE_SAVED_OPERANDS(FAST_STORE_SAVED_OPERANDS)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_SAVED_STORE_OPERANDS_PARALLEL_ADMISSION_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],FAST_STORE_SAVED_OPERANDS=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],FAST_STORE_SAVED_OPERANDS=1,
        saved_store_operands_new_ff_bits=0,saved_store_operands_new_sram_bits=0,saved_store_operands_new_pipeline_edges=0,
        saved_store_operands_additional_prf_read_ports=0,fast_store_late_capacity_choices=2)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Fast-store eligibility uses original saved PRF readiness and fallback address predicates only when neither source has a current matching legal WB. Matching WB or unready sources retain original RS/ALU execution without an added dispatch hold. Actual LSQ address/data remain original. Precompute ordinary RS demand and capacity with one fewer RS allocation, selecting only the final bool with the at-most-one fast store. Preserve original conservative D replacement credit.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        measured_basis='A83 actual4.032ns memory-response to CDB/PRF WB address classifier to D admission to LSQ GEN owner path',
        wb_store_address_classification_removed_from_fast_eligibility=True,
        late_fast_store_population_count_and_capacity_comparison_removed=True,
        saved_store_operands_limit='No new wait edge or D stall; gives up fast completion for current WB-assisted stores while retaining their original RS execution. Removes measured WB value/adder/classification and late demand-count/compare serialization, but WB valid/phys to bypass guard and stored-address paths remain. Gate mapping, Fmax, IPC coverage cost and total area unknown.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,additional_prf_read_ports=0,
        source_arguments=[
            'A83 measured critical path traverses CDB WB value distribution2.292ns, store WB-candidate address high bit2.755ns and D admission/payload3.319ns before LSQ GEN write3.830ns. New private PRF queries use the original stored read tree/ready and existing stored fallback sum; no data read port, adder, state or SRAM is added. Public PRF data/readiness/address selection and write priorities remain original.',
            'Stored-ready is P0 or original selected current stored ready. Illegal/padding phys IDs remain unready. Current bypass-pending is the exact existing OR of legal valid WB matches, including all lanes and duplicate write identities. Both stored-ready and no pending match are required, including data source. Thus the public selected source values are stored values, and the selected allocation address equals the exact stored fallback sum, with all carry/wrap/sign12 behavior preserved. No assumption about repeated WB of ready physical registers is needed.',
            'Active profile requires saved DISPATCH_PIPELINE, original early address/data allocation and parallel stored sum. A valid store with both private source ready bits consequently satisfies the original lsq_alloc_addr_valid/data_valid. Those redundant public WB-ready dependencies are omitted only in that profile. RAM/size/alignment/canonical immediate/zero explicit data/type restrictions, real atomic LSQ allocation and current complete ROB identity checks stay intact. Matching WB falls back to original RS; no extra D stall or artificial lost replacement credit.',
            'At most one store_without_agu bit is true for both original lowest-ready and saved lowest-potential identity modes. Store !load makes this bit disjoint from load_without_agu. Let base popcount(d_valid & ~load_without_agu)=B and F=OR(store_without_agu). Actual RS demand=B-F. B-F<=free iff B<=free OR(F AND B<=free+1), exactly the new two-case condition. F1 implies B>=1; the free+1 computation is extended17bits. Actual per-lane d_rs_need/allocator outputs and LSQ demand are unchanged.',
            'Original d_replace_credit block is byte-identical and counts all valid lanes, so still implies ordinary capacity and d_admit for every saved packet. No credit-to-PRF or R-to-D eligibility loop is introduced. Current WB data still feeds actual LSQ payload/write FF, but cannot enter fast eligibility through address class; current WB valid/phys may still reach the final capacity choice through no-bypass qualification. Stored sum/class and load readiness may become separate timing limits.',
            'Default0/unsupported parallel or fast-store profile retains the old actual-address/readiness and d_rs_demand comparison. Private outputs are0 in inactive/nonparallel branches; standalone callers can leave them unconnected. Full A84-A86 head retirement/ACK behavior is inherited, not independently measured. No new FF/SRAM/edge; gates and lost same-cycle WB fast-store coverage need later aggregate evaluation.',
            'Source and ownership review only. No HDL/lint/formal/simulation/synthesis/STA/unit tests. Future coherent coverage includes P0/illegal phys, stored-ready/unready with all WB lanes and duplicate sources, simultaneous allocate/WB, positive/negative/wrapped addresses, MMIO/RAM boundaries and alignment, full RS/LSQ, all fast-store source/identity/default modes, credit/replacement, branch recovery/full GEN, full RV32IM and course performance. No measured gain or objective completion is claimed.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
