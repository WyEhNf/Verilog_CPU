"""Use bounded direct row selects for only the2/3-bit predictor direction reads."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A50_predictor_direction_independent_target'
TARGET = BASE / 'A51_predictor_narrow_direction_read'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A51_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/common/rv32_asap7_fanout.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    helper = '''

// Narrow table read: each row hit directly drives at most four data masks.
// Retain the original four-row index distribution and balanced OR reduction;
// wide payload reads still use the original bounded word/select trees.
module rv32_frequency_narrow_array_read #(
    parameter integer WIDTH=3,ENTRIES=64,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer DOMAINS=(ENTRIES+3)/4,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [INDEX_WIDTH-1:0] index_i,
    output wire [WIDTH-1:0] value_o
);
    wire [DOMAINS*INDEX_WIDTH-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(INDEX_WIDTH),.LEAVES(DOMAINS)) query_tree (
        .signal_i(index_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES) begin:g_present
                wire hit=query_views[(row/4)*INDEX_WIDTH +: INDEX_WIDTH]==row;
                assign reads[LEAVES+row]={WIDTH{hit}} & rows_i[row*WIDTH +: WIDTH];
            end else begin:g_padding
                assign reads[LEAVES+row]=0;
            end
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_reduce
            assign reads[node]=reads[2*node] | reads[2*node+1];
        end
    endgenerate
    initial begin
        if(WIDTH<1 || WIDTH>4)
            $fatal(1,"Narrow array read width must be1..4");
    end
endmodule
'''
    assert 'module rv32_frequency_narrow_array_read' not in original
    text = original + helper
    assert not re.search(r'\breg\b|\balways\b|posedge|negedge', helper)
    changes[name] = text
    name = 'rtl/predictor/rv32_branch_predictor.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer DIRECTION_INDEPENDENT_TARGET = 0,',
        '    parameter integer DIRECTION_INDEPENDENT_TARGET = 0,\n    parameter integer NARROW_DIRECTION_READ = 0,')
    for instance, width, entries, index_width, rows, index, result, indent in (
        ('bht_query', 3, 'BHT_ENTRIES', 'BHT_INDEX_WIDTH', 'bht_rows', 'query_bht_index', 'query_bht_word', '    '),
        ('bimodal_query', 3, 'BHT_ENTRIES', 'BHT_INDEX_WIDTH', 'bimodal_rows', 'query_pc_i[9:2+BANK_BITS]', 'query_bimodal_word', '        '),
        ('choice_query', 2, 'CHOICE_ENTRIES', 'CHOICE_INDEX_WIDTH', 'choice_rows', 'query_pc_i[7:2+BANK_BITS]', 'query_choice', '        ')):
        old = f'''{indent}rv32_frequency_array_read #(.WIDTH({width}),.ENTRIES({entries}),.INDEX_WIDTH({index_width})) {instance} (
{indent}    .rows_i({rows}),.index_i({index}),.value_o({result}));'''
        # The top-level BHT read needs generate; the other reads are already
        # nested in g_hybrid_direction and use the existing generate context.
        begin = 'generate ' if instance == 'bht_query' else ''
        end = ' endgenerate' if instance == 'bht_query' else ''
        new = f'''{indent}{begin}if(NARROW_DIRECTION_READ!=0) begin:g_narrow_{instance}
{indent}    rv32_frequency_narrow_array_read #(.WIDTH({width}),.ENTRIES({entries}),.INDEX_WIDTH({index_width})) query (
{indent}        .rows_i({rows}),.index_i({index}),.value_o({result}));
{indent}end else begin:g_regular_{instance}
{indent}    rv32_frequency_array_read #(.WIDTH({width}),.ENTRIES({entries}),.INDEX_WIDTH({index_width})) query (
{indent}        .rows_i({rows}),.index_i({index}),.value_o({result}));
{indent}end{end}'''
        text = once(text, old, new)
    # Do not change any training/table owner or downstream prediction logic.
    a = '    always @* begin\n        pred_taken_o';
    assert text[text.index(a):] == original[original.index(a):]
    assert text.count('rv32_frequency_narrow_array_read #') == 3
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text
    name = 'rtl/predictor/rv32_banked_predictor.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer DIRECTION_INDEPENDENT_TARGET = 0,',
        '    parameter integer DIRECTION_INDEPENDENT_TARGET = 0,\n    parameter integer NARROW_DIRECTION_READ = 0,')
    text = once(text, '.DIRECTION_INDEPENDENT_TARGET(DIRECTION_INDEPENDENT_TARGET),',
        '.DIRECTION_INDEPENDENT_TARGET(DIRECTION_INDEPENDENT_TARGET), .NARROW_DIRECTION_READ(NARROW_DIRECTION_READ),')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_DIRECTION_INDEPENDENT_TARGET = 0,',
        '    parameter integer PREDICTOR_DIRECTION_INDEPENDENT_TARGET = 0,\n    parameter integer PREDICTOR_NARROW_DIRECTION_READ = 0,')
    text = once(text, '.DIRECTION_INDEPENDENT_TARGET(PREDICTOR_DIRECTION_INDEPENDENT_TARGET && COMPACT_TARGET_ACTIVE),',
        '.DIRECTION_INDEPENDENT_TARGET(PREDICTOR_DIRECTION_INDEPENDENT_TARGET && COMPACT_TARGET_ACTIVE),\n                .NARROW_DIRECTION_READ(PREDICTOR_NARROW_DIRECTION_READ),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_DIRECTION_INDEPENDENT_TARGET = 1,',
        '    parameter integer PREDICTOR_DIRECTION_INDEPENDENT_TARGET = 1,\n    parameter integer PREDICTOR_NARROW_DIRECTION_READ = 1,')
    text = once(text, '.PREDICTOR_DIRECTION_INDEPENDENT_TARGET(PREDICTOR_DIRECTION_INDEPENDENT_TARGET),',
        '.PREDICTOR_DIRECTION_INDEPENDENT_TARGET(PREDICTOR_DIRECTION_INDEPENDENT_TARGET), .PREDICTOR_NARROW_DIRECTION_READ(PREDICTOR_NARROW_DIRECTION_READ),')
    changes[name] = text
    for name in parent['source_sha256']:
        dst = TARGET / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dst)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], PREDICTOR_NARROW_DIRECTION_READ=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], predictor_narrow_direction_read=True,
        predictor_direction_row_hit_data_fanout_maximum=3,
        predictor_direction_read_index_domains_four_rows=True,
        predictor_direction_read_removed_source_inverters_before_pruning=1152,
        predictor_narrow_direction_read_added_ff_bits=0, predictor_narrow_direction_read_added_sram_bits=0,
        predictor_narrow_direction_read_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Replace only the gshare/bimodal3-bit and chooser2-bit direction query helpers with a functional narrow read: keep four-row index distribution, exact row equality/padding and balanced OR tree, and let the row hit directly drive at most3 data masks. Remove the two retained row-select inversions required only for wide words; preserve all table state, training, target and history behavior.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        narrow_direction_removed_source_inversions_before_pruning=2*(256+256+64),
        removed_inverter_literal_area_component_um2=2*(256+256+64)*0.04374,
        actual_mapped_gate_savings_and_total_area_unknown=True,
        predictor_narrow_direction_read_unmeasured=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PREDICTOR_NARROW_DIRECTION_READ_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        removed_source_inverters_before_pruning=1152,
        source_arguments=[
            'For every row, the old LEAVES1 select_tree is two real retained inversions of row equality, so its positive output equals hit. The new mask uses that same hit directly. Same distributed query, equality width, zero padding and balanced OR reduction means the same row data/invalid-index result in ordinary binary operation. No new data interpretation or predicted behavior is introduced.',
            'Use this helper only for the3-bit gshare/bimodal row and2-bit chooser row. A hit directly drives at most3 mask gates in these call sites; query index leaves still own four opposite row comparisons. All original wide BTB/payload/cache/ROB/LSQ readers retain their old electrical-domain controls. The helper rejects widths outside1..4.',
            'Across all FE1/2/4 bank configurations, the active hybrid tables contain256+256+64 rows, giving1152 removed retained row-select inverter instances before pruning. At0.04374um2 per mapped INVx1, their literal component is50.38848um2; this is not a prediction of actual gate count or total-area savings because synthesis can resize/refactor/prune other logic.',
            'All row state, saturation/first-training behavior, history/index hashing, exact prediction-time metadata, multi-feedback arbitration, target/RAS and speculative recovery source remain unchanged. The existing direction/trained/choice read results feed the same prediction logic with no added stage or owner.',
            'Default mode0 elaborates original helpers. Course mode1 enables only the specified narrow direction call sites. No FF/SRAM state or fetch/execute boundary is added. Removing two serial kept inversions targets the direction query path, but actual load/slew and Fmax must be measured on the complete candidate.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Future meaningful coverage includes all table rows, invalid-index zero padding, FE1/2/4, hybrid-off and cold/trained rows, simultaneous accepted training/query and metadata/recovery, plus the complete batch native course measurement.'
        ])
    write(BASE / 'A51_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
