"""Move held ROB bank decoding ahead of the original held-slot read."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import ROOT, read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A100_held_report_identity_query'
TARGET = BASE/'A101_held_identity_row_query'
REVIEW = BASE/'A101_source_review.json'


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json') == '9f2025e9d7e5a07055d68f88d81f98805ff3540552ddaa939076cdf750ee83b4'
    parent = read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    begin = original.index('            wire [LSQ_ENTRIES*ROB_TAG_WIDTH-1:0] held_rows;')
    end = original.index('            assign load_report_identity_tags_o={head_tag,normal_identity_tree',begin)
    replacement = '''            wire [LSQ_ENTRIES*NORMAL_IDENTITY_WIDTH-1:0] held_rows;
            wire [NORMAL_IDENTITY_WIDTH-1:0] held_identity;
            for(genvar held_row=0;held_row<LSQ_ENTRIES;held_row=held_row+1) begin:g_row
                wire [ROB_TAG_WIDTH-1:0] tag=rob_tag_mem[held_row];
                wire [REPORT_ROB_QUERY_WIDTH-1:0] query;
                for(genvar held_low=0;held_low<REPORT_ROB_LOW_ROWS;held_low=held_low+1) begin:g_low
                    assign query[held_low]=tag[3 +: REPORT_ROB_LOW_BITS]==held_low;
                end
                for(genvar held_high=0;held_high<REPORT_ROB_HIGH_ROWS;held_high=held_high+1) begin:g_high
                    if(REPORT_ROB_HIGH_BITS>0) begin:g_bits
                        assign query[REPORT_ROB_LOW_ROWS+held_high]=
                            tag[3+REPORT_ROB_LOW_BITS +: REPORT_ROB_HIGH_BITS]==held_high;
                    end else begin:g_single_bank
                        assign query[REPORT_ROB_LOW_ROWS+held_high]=1'b1;
                    end
                end
                assign held_rows[held_row*NORMAL_IDENTITY_WIDTH +: NORMAL_IDENTITY_WIDTH]={query,tag};
            end
            // Decode saved ROB banks before selecting the held LSQ row. Late
            // held-slot selection routes the original full tag and prepared
            // query together, avoiding tag mux -> bank decode -> ROB lookup.
            // Original full LSQ range/valid/complete/GEN still qualifies H.
            rv32_frequency_array_read #(.WIDTH(NORMAL_IDENTITY_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) held_reader (
                .rows_i(held_rows),.index_i(report_hold_tag[TAG_SLOT_LSB +: SLOT_WIDTH]),
                .value_o(held_identity));
            assign load_report_held_identity_tag_o=held_identity[0 +: ROB_TAG_WIDTH];
            assign load_report_held_identity_query_o=held_identity[ROB_TAG_WIDTH +: REPORT_ROB_QUERY_WIDTH];
'''
    text = original[:begin]+replacement+original[end:]
    for marker in ['    generate if(REPORT_ROB_PREDECODE!=0) begin:g_report_rob_query',
        '            assign load_report_identity_tags_o={head_tag,normal_identity_tree']:
        assert text[text.index(marker):] == original[original.index(marker):]
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    name = 'rtl/backend/rv32_lsq.v'
    (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_HELD_SLOT_READ_WITH_PER_ROW_ROB_QUERY_PREDECODE_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(TARGET),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=[name],
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['enabled_profile'] = dict(parent['enabled_profile'],held_identity_per_row_bank_query=1,
        held_identity_row_query_new_ff_bits=0,held_identity_row_query_new_sram_bits=0,
        held_identity_row_query_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Decode complete saved ROB slot low/high bank query independently for every LSQ row before held-slot selection. Original held array reader width grows from ROB_TAG_WIDTH to ROB_TAG_WIDTH+REPORT_ROB_QUERY_WIDTH and routes {query,tag} together; all full tag/GEN qualification and late H boolean selection retained. Removes held-slot -> encoded ROBtag mux -> bankdecode dependency; extra query routing/driver combination area unknown. Original A100 normal/head/public/state code byte-identical.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        held_row_query_limit='A100 separates late H from ROB qualification but its held candidate still reads encoded16bit ROBtag before12bit bank decoding then9bit ROB live read. A101 performs bank decode of each saved row before held slot is available; selected packet28bits includes preparedquery plus all16tagbits. Course tags/query decoded elsewhere per same row, allowing potential shared decode. New12bit routed query/wordselect driver may cost area or fanout; not measured and not guaranteed critical until A99 result.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=[name],tests_started=False,
        new_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,new_rob_live_queries=0,
        source_arguments=[
            'For any in-range held LSQ indexr, original reader returns rob_tag_mem[r], then low/high query bits are equalities on its ROBslot slices. New rowr packet is exactly {decode(rob_tag_mem[r]),rob_tag_mem[r]}, using same low/high slice/constant high0 rule. Original array_read onehot rowhit returns that packet for every binary indexr, so full tag and query outputs equal original for all saved tag values, without generation or reachable-state assumptions.',
            'Out-of-range held index may return zero preparedquery rather than decode(zeroTag); returnedTag remains0 and tag[0]=0 forces candidate_live false. OriginalH cannot be true without fulltag_matches_slot selecting a real row; thus no out-of-range private value can authorize a new event. Normal/head choice and all actual qualification, eightROBGEN/nineLSQGEN, range/live/complete/reported/reset/flush/recovery/held-valid rules retained.',
            'Only source block inside active independent held identity changes. Defaultnewmode remains enabled only via existing A100 HELD_LOAD_IDENTITY_ACTIVE guard; flag0/deactivated profile original fallback identical. Entire LSQ suffix from normal/head private outputs through publicquery/publicpayload and clocked state/helper remains byte-identical. Backend/core/top/source parameters unchanged, so no new handshake, portwidth, state or pipelineedge.',
            'Potential stage gain is elimination of serial selected encoded ROBslot -> bank decoder before current ROBlive read. Course held routing grows16->28bits using original at-most16bit leaf control distribution; additional12bit LSQ mux and one wordselect driver per row can increase combination area. Original per-row decode for normal/head query may share afterflattening, but sharing/area/frequency not guaranteed. No measured IPC/PPA or adoption claim.',
            'A99 original measurement remains separate and immutable. No newHDL/lint/formal/sim/synthesis/STA/unit tests or CPU build. Use actual A99 PPA and nextpath evidence to decide whether A100/A101 are worth a coherent pre-reported batch; maintain full RV32IM/OoO/in-ordercommit/MMIO/parameter requirements and three numeric targets. Full19correctness and M/GEN/recovery/MMIO/parameter coverage before adoption.'
        ],goal_complete=False,adopted=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
