"""Prepare an independent exact numeric-age order cache for the complete RS.

Keep every original age word and age-counter wrap rule. Cache the comparison
of each pair at the same allocation edge instead of repeatedly comparing all
stored ages in the issue path. This adds derived state, no execution cycle.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source,out = args.source_root.resolve(),args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh age-matrix candidate directory')
    relative = Path('rtl/backend/rv32_reservation_station.v')
    original = source/relative
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(original) == '9dbf90f1121ac3f0495b4910a3c42502d167db036c50fec49cdd3307a507365f'
    code = original.read_text()
    def replace(before,after):
        nonlocal code
        assert code.count(before) == 1, 'Ambiguous source anchor: '+before
        code = code.replace(before,after,1)
    replace('    parameter integer ALLOC_STATIC_WRITE = 0,',
            '    parameter integer ALLOC_STATIC_WRITE = 0,\n    parameter integer AGE_ORDER_MATRIX = 0,')
    replace('    wire [COUNT_WIDTH-1:0] ready_rank [0:ENTRIES-1];',
            '    wire [COUNT_WIDTH-1:0] ready_rank [0:ENTRIES-1];\n'
            '    wire [ENTRIES-1:0] cached_age_precedes [0:ENTRIES-1];')
    replace('wire older = (age_mem[rank_other] < age_mem[rank_slot]) ||\n'
            '                        ((rank_other < rank_slot) && (age_mem[rank_other] == age_mem[rank_slot]));',
            'wire older = ((AGE_ORDER_MATRIX != 0) && (ALLOC_STATIC_WRITE != 0)) ?\n'
            '                        cached_age_precedes[rank_other][rank_slot] :\n'
            '                        ((age_mem[rank_other] < age_mem[rank_slot]) ||\n'
            '                         ((rank_other < rank_slot) && (age_mem[rank_other] == age_mem[rank_slot])));')
    replace('    wire [ENTRIES-1:0] alloc_row_write;',
            '    wire [ENTRIES-1:0] alloc_row_write;\n'
            '    wire [BE_WIDTH-1:0] alloc_row_grants [0:ENTRIES-1];')
    replace('            assign alloc_row_write[ar] = |allocation_match_bits;',
            '            assign alloc_row_grants[ar] = grants;\n'
            '            assign alloc_row_write[ar] = |allocation_match_bits;')
    insert = '''    // Cache the exact unsigned numeric comparison, including age-counter
    // wrap and equal-age slot tie breaks. Only allocation changes an age;
    // flush and issue preserve both age words and their derived relation.
    // Shared new-age/old-age comparisons are computed once per lane/row.
    genvar age_lane, age_row, age_peer, pair_low, pair_high;
    generate if ((AGE_ORDER_MATRIX != 0) && (ALLOC_STATIC_WRITE != 0)) begin : g_age_order_matrix
        wire [AGE_WIDTH-1:0] new_age [0:BE_WIDTH-1];
        wire [BE_WIDTH-1:0] new_le_old [0:ENTRIES-1];
        wire [BE_WIDTH-1:0] new_lt_old [0:ENTRIES-1];
        wire [BE_WIDTH-1:0] new_le_new [0:BE_WIDTH-1];
        for (age_lane = 0; age_lane < BE_WIDTH; age_lane = age_lane + 1) begin : g_new_age
            assign new_age[age_lane] = age_counter + age_lane;
            for (age_row = 0; age_row < ENTRIES; age_row = age_row + 1) begin : g_old_age
                assign new_le_old[age_row][age_lane] = new_age[age_lane] <= age_mem[age_row];
                assign new_lt_old[age_row][age_lane] = new_age[age_lane] < age_mem[age_row];
            end
            for (age_peer = 0; age_peer < BE_WIDTH; age_peer = age_peer + 1) begin : g_peer_age
                assign new_le_new[age_lane][age_peer] = new_age[age_lane] <= new_age[age_peer];
            end
        end
        for (pair_low = 0; pair_low < ENTRIES; pair_low = pair_low + 1) begin : g_low
            assign cached_age_precedes[pair_low][pair_low] = 1'b0;
            for (pair_high = pair_low + 1; pair_high < ENTRIES; pair_high = pair_high + 1) begin : g_high
                reg low_precedes_high;
                reg left_new_order, right_new_order, both_new_order;
                integer left_lane, right_lane;
                always @* begin
                    left_new_order = 1'b0;
                    right_new_order = 1'b0;
                    both_new_order = 1'b0;
                    for (left_lane = 0; left_lane < BE_WIDTH; left_lane = left_lane + 1) begin
                        left_new_order = left_new_order |
                            (alloc_row_grants[pair_low][left_lane] && new_le_old[pair_high][left_lane]);
                        right_new_order = right_new_order |
                            (alloc_row_grants[pair_high][left_lane] && !new_lt_old[pair_low][left_lane]);
                        for (right_lane = 0; right_lane < BE_WIDTH; right_lane = right_lane + 1)
                            both_new_order = both_new_order | (alloc_row_grants[pair_low][left_lane] &&
                                alloc_row_grants[pair_high][right_lane] && new_le_new[left_lane][right_lane]);
                    end
                end
                always @(posedge clk_i) begin
                    if (reset_i)
                        low_precedes_high <= 1'b1;
                    else if (!flush_valid_i) begin
                        if (alloc_row_write[pair_low])
                            low_precedes_high <= alloc_row_write[pair_high] ? both_new_order : left_new_order;
                        else if (alloc_row_write[pair_high])
                            low_precedes_high <= right_new_order;
                    end
                end
                assign cached_age_precedes[pair_low][pair_high] = low_precedes_high;
                assign cached_age_precedes[pair_high][pair_low] = !low_precedes_high;
            end
        end
    end endgenerate

'''
    replace('    // Allocate a contiguous prefix and choose the oldest ready entries for',
            insert+'    // Allocate a contiguous prefix and choose the oldest ready entries for')
    (out/relative).parent.mkdir(parents=True)
    (out/relative).write_text(code)
    (out/'baseline').mkdir()
    shutil.copyfile(original,out/'baseline/rv32_reservation_station.v')
    report = dict(status='PREPARED_NOT_VALIDATED',main_tree_modified=False,integrated_into_cpu=False,
                  source=str(original),source_sha256=digest(original),candidate_sha256=digest(out/relative),
                  preparer_sha256=digest(Path(__file__)),new_parameter='AGE_ORDER_MATRIX',
                  prerequisite_parameter={'ALLOC_STATIC_WRITE':1},original_age_state_retained=True,
                  added_bits='ENTRIES*(ENTRIES-1)/2',new_pipeline_cycles=0,
                  scope='Caches original unsigned age comparisons; does not change wrap ordering or issue policy')
    (out/'candidate_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Prepared independent RS age-order matrix candidate: '+str(out))


if __name__ == '__main__':
    main()
