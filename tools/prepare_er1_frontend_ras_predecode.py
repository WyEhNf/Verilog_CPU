"""Prepare fixed-word RAS predecode independently of the frozen A55 measurement."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A55_predictor_bank_local_prefix_history'
TARGET = BASE / 'A56_frontend_ras_predecode'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def call_expression(inst):
    return (f"(({inst}[6:0]==7'b1101111) || ({inst}[6:0]==7'b1100111 && {inst}[14:12]==3'b000)) && "
            f"({inst}[11:7]==5'd1 || {inst}[11:7]==5'd5)")


def return_expression(inst):
    return (f"{inst}[6:0]==7'b1100111 && {inst}[14:12]==3'b000 && {inst}[11:7]==5'd0 && "
            f"({inst}[19:15]==5'd1 || {inst}[19:15]==5'd5) && {inst}[31:20]==12'd0")


def main():
    assert not TARGET.exists() and not (BASE / 'A56_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/cpu_core.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer FRONTEND_PARALLEL_BUNDLE_CONTROL = 0,',
        '    parameter integer FRONTEND_PARALLEL_BUNDLE_CONTROL = 0,\n    parameter integer FRONTEND_RAS_PREDECODE = 0,')
    text = once(text, '    reg [31:0] ras_inst;\n', '')
    text = once(text, '    wire [FE_WIDTH*32-1:0] ras_query_words;',
        f'''    wire [FE_WIDTH*2-1:0] ras_query_flags;
    wire [7:0] ras_line_flags;
    generate if(FRONTEND_RAS_PREDECODE!=0) begin:g_ras_line_predecode
        for(genvar word=0;word<4;word=word+1) begin:g_word
            wire [31:0] line_inst=if_resp_line_data[word*32 +: 32];
            assign ras_line_flags[word*2+1]={call_expression('line_inst')};
            assign ras_line_flags[word*2]={return_expression('line_inst')};
        end
    end else begin:g_no_ras_line_predecode
        assign ras_line_flags=8'b0;
    end endgenerate''')
    text = once(text, '''            wire [31:0] query_inst;
            rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_query (
                .rows_i(if_resp_line_data),.index_i(query_word_index),.value_o(query_inst));
            assign ras_query_words[predictor_lane*32 +: 32]=query_inst;''',
        f'''            wire [1:0] query_ras_flags;
            if(FRONTEND_RAS_PREDECODE!=0) begin:g_predecoded_ras_query
                rv32_frequency_narrow_array_read #(.WIDTH(2),.ENTRIES(4),.INDEX_WIDTH(3)) flags_query (
                    .rows_i(ras_line_flags),.index_i(query_word_index),.value_o(query_ras_flags));
            end else begin:g_original_ras_query
                wire [31:0] query_inst;
                rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_query (
                    .rows_i(if_resp_line_data),.index_i(query_word_index),.value_o(query_inst));
                assign query_ras_flags[1]={call_expression('query_inst')};
                assign query_ras_flags[0]={return_expression('query_inst')};
            end
            assign ras_query_flags[predictor_lane*2 +: 2]=query_ras_flags;''')
    text = once(text, '''            wire query_is_return = (query_inst[6:0] == 7'b1100111) &&
                                   (query_inst[14:12] == 3'b000) &&
                                   (query_inst[11:7] == 5'd0) &&
                                   ((query_inst[19:15] == 5'd1) ||
                                    (query_inst[19:15] == 5'd5)) &&
                                   (query_inst[31:20] == 12'd0);''',
        '            wire query_is_return = query_ras_flags[0];')
    text = once(text, '        ras_inst = 32\'d0;\n', '')
    text = once(text, '''                    ras_inst = ras_query_words[ras_lane*32 +: 32];
                    if (((ras_inst[6:0] == 7'b1101111) ||
                         ((ras_inst[6:0] == 7'b1100111) &&
                          (ras_inst[14:12] == 3'b000))) &&
                        ((ras_inst[11:7] == 5'd1) ||
                         (ras_inst[11:7] == 5'd5))) begin''',
        '                    if (ras_query_flags[ras_lane*2+1]) begin')
    text = once(text, '''                    end else if ((ras_inst[6:0] == 7'b1100111) &&
                                 (ras_inst[14:12] == 3'b000) &&
                                 (ras_inst[11:7] == 5'd0) &&
                                 ((ras_inst[19:15] == 5'd1) ||
                                  (ras_inst[19:15] == 5'd5)) &&
                                 (ras_inst[31:20] == 12'd0)) begin''',
        '                    end else if (ras_query_flags[ras_lane*2]) begin')
    marker = '    // The first accepted call wins; return/taken events close the'
    assert text[text.index(marker):] == original[original.index(marker):]
    assert 'ras_query_words' not in text and 'ras_inst' not in text
    assert text.count('always @(posedge clk)') == original.count('always @(posedge clk)')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_PARALLEL_BUNDLE_CONTROL = 1,',
        '    parameter integer FRONTEND_PARALLEL_BUNDLE_CONTROL = 1,\n    parameter integer FRONTEND_RAS_PREDECODE = 1,')
    text = once(text, '.FRONTEND_PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL),',
        '.FRONTEND_PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL), .FRONTEND_RAS_PREDECODE(FRONTEND_RAS_PREDECODE),')
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], FRONTEND_RAS_PREDECODE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], frontend_ras_predecode=True,
        ras_depth_unchanged=4, ras_query_selection_width=2,
        ras_predecode_added_ff_bits=0, ras_predecode_added_sram_bits=0, ras_predecode_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Predecode call/return flags once for each fixed line word and select only2 bits per fetch lane, replacing PC-selected32-bit instruction reads before RAS classification. Same call/return predicates, line bounds, prefix priority and accept events; four-entry stack state/targets and all downstream fetch/retirement logic unchanged.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        ras_pc_to_wide_instruction_mux_then_decode_dependency_removed=True,
        ras_predecode_mapped_area_frequency_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_FRONTEND_RAS_PREDECODE_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'For a defined selected line word, decoding after the old32-bit read equals decoding that fixed word first and selecting its2-bit call/return flags. Invalid query_word_index>=4 previously returned a zero instruction, whose call/return predicates are both0; the new padded flag read also returns00. This is a binary source argument, not HDL equivalence or arbitrary-X semantics proof.',
            'Call is JAL or funct3=0 JALR with rd1/5; return is funct3=0 JALR with rd0, rs1=1/5 and imm0. Both predicates are exactly the original comparisons. Prefix still selects the first call, then return, then effective predicted-taken instruction; an empty-stack return still terminates RAS event search without popping.',
            'The query return override retains query_valid, ENABLE_PREDICTOR, nonempty ras_count and the original32-bit ras_target. if_resp_valid&&if_resp_ready acceptance gates are unchanged, including existing error/redirect handling. No new speculative-stack checkpoint or recovery policy is claimed.',
            'All source from the existing RAS return-address payload selector onward is byte-exact: four32-bit stack owners, stack pointer/count reset/push/pop priority, full PC+4 return address, frontend/decode/backend/cache/commit wiring. A removed32-bit ras_inst temporary was combinational only, not a register bank. Internal diagnostic temporary hierarchy changes, not architectural output/state.',
            'Mode0 retains original32-bit instruction read with equivalent local flag decode. Core default0, course top1; FE1/2/4 use the unchanged3-bit line-word index and bounds. Mode1 uses the existing stateless narrow array read, reducing dynamic query data width32 to2. Fixed-word decode cost and buffers remain unmeasured; no frequency/IPC/area number is assigned.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Prepared independently while A55R2 uses its frozen older source. Future coverage includes FE1/2/4/all line starts, call rd1/5, JALR funct3/rs1/imm filters, empty/full/wrapping RAS, call/return/taken prefix precedence, accept/backpressure/error/reset/redirect and mode0 fallback.'
        ])
    write(BASE / 'A56_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
