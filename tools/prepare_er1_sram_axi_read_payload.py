"""Store first three AXI words in course SRAM, retain final word FF; no tests."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A24_sram_instruction_filter'
TARGET=BASE/'A25_sram_axi_read_payload'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/course/rv32_axi_lite_bridge.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer RESPONSE_FIFO_DEPTH = 0',
        '    parameter integer READ_PAYLOAD_SRAM = 0,\n    parameter integer RESPONSE_FIFO_DEPTH = 0')
    old='''            for(payload_word=0;payload_word<4;payload_word=payload_word+1) begin:g_word
                rv32_frequency_word_bank #(.WIDTH(32)) word_owner (
                    .clk_i(clock),.write_i(return_valid && return_slot==payload_row && return_word==payload_word),
                    .data_i(read_return_data[(payload_row/4)*32 +: 32]),.data_o(read_data[payload_row][payload_word*32 +: 32]));
            end'''
    new='''            if(READ_PAYLOAD_SRAM!=0) begin:g_sram_words
                wire row_return=return_valid && return_slot==payload_row;
                wire write_prefix=row_return && return_word!=2'd3;
                wire [31:0] word_data=read_return_data[(payload_row/4)*32 +: 32];
                // AXI-Lite returns the issued words in FIFO order 0,1,2,3.
                // On the final-word edge this prefix bank reads, while word3
                // is captured independently. All 128 bits are ready when the
                // unchanged received==4 condition publishes the line.
                // Reread on idle edges: FakeRAM Q does not retain idle data.
                sram_fakeram #(.DEPTH(1),.WIDTH(96),.WRITE_GRANULARITY(32)) prefix (
                    .clk(clock),.en(!reset),.we(write_prefix),
                    .wmask(3'b001 << return_word),.addr(1'b0),
                    .wdata({3{word_data}}),.rdata(read_data[payload_row][95:0]));
                rv32_frequency_word_bank #(.WIDTH(32)) final_word (
                    .clk_i(clock),.write_i(row_return && return_word==2'd3),
                    .data_i(word_data),.data_o(read_data[payload_row][127:96]));
            end else begin:g_register_words
                for(payload_word=0;payload_word<4;payload_word=payload_word+1) begin:g_word
                    rv32_frequency_word_bank #(.WIDTH(32)) word_owner (
                        .clk_i(clock),.write_i(return_valid && return_slot==payload_row && return_word==payload_word),
                        .data_i(read_return_data[(payload_row/4)*32 +: 32]),.data_o(read_data[payload_row][payload_word*32 +: 32]));
                end
            end'''
    text=once(text,old,new)
    assert 'read_received[candidate_row]==4' in original
    assert '.data_i({read_issue_slot,query_read_issue_sent[1:0]})' in original
    # Preserve all arbitration, AXI channels, queue metadata and lifecycle state.
    head_end='    genvar payload_row,payload_word;'
    original_head=original[:original.index(head_end)]
    new_head=text[:text.index(head_end)].replace('    parameter integer READ_PAYLOAD_SRAM = 0,\n','')
    assert new_head==original_head
    suffix='        for(payload_row=0;payload_row<WRITE_LINES;payload_row=payload_row+1)'
    assert text[text.index(suffix):]==original[original.index(suffix):]
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer AXI_RESPONSE_FIFO_DEPTH = 2',
        '    parameter integer AXI_READ_PAYLOAD_SRAM = 1,\n    parameter integer AXI_RESPONSE_FIFO_DEPTH = 2')
    text=once(text,'.WORD_QUEUE(WORD_QUEUE), .RESPONSE_FIFO_DEPTH(AXI_RESPONSE_FIFO_DEPTH)',
        '.WORD_QUEUE(WORD_QUEUE), .READ_PAYLOAD_SRAM(AXI_READ_PAYLOAD_SRAM), .RESPONSE_FIFO_DEPTH(AXI_RESPONSE_FIFO_DEPTH)')
    changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],AXI_READ_PAYLOAD_SRAM=1)
    record['enabled_profile']=dict(parent['enabled_profile'],AXI_READ_PAYLOAD_SRAM=1,
        axi_read_prefix_sram_bits=768,axi_read_final_word_ff_bits=256,
        axi_read_payload_removed_ff_bits=768,axi_read_payload_added_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Place the first three words of each AXI read line in masked synchronous SRAM; keep final returned word in FF so unchanged received==4 publication has all data on the original edge.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        axi_read_payload_removed_ff_bits=768,axi_read_removed_ff_area_um2=768*.2916,
        axi_read_added_course_sram_area_um2=24*round(32*.0419904,6),
        axi_read_payload_added_edges=0,axi_read_payload_ipc_ppa_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_AXI_PREFIX_SRAM_FINAL_WORD_REGISTER_NO_EXTRA_EDGE_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        changed_files=list(changes),tests_started=False,source_arguments=[
            'Each issued AR writes its current read_sent[1:0] and line slot into the existing order FIFO; read_sent increments exactly on AR acceptance. R responses pop that FIFO. AXI-Lite ordering therefore delivers each line in word order0,1,2,3.',
            'Prefix SRAM writes only word0..2 with corresponding one-hot32-bit mask. Word3 uses the original FF owner. On its edge all prefix banks read, making SRAM Q and final word simultaneously available while received count changes to4.',
            'Existing read-reply eligibility requires read_valid&&read_received==4; all arbitration/AXI handshakes, slot allocation/reset/lifetime, error accumulation, metadata/order queues and response FIFO remain exact parent bytes.',
            'Prefix RAM rereads on every nonreset idle edge, preserving Q while a completed line awaits FIFO capacity; no new state, response delay, handshake or metadata capacity is added.',
            'Course profile removes768 data FFs (223.9488um2 at measured DFF unit price) and adds768 SRAM bits (32.248632um2 with24 macro rounding). This excludes command and read selection costs and is not measured net total area.',
            'Depth1 is explicitly permitted by the frozen course public RAM interface. All SRAM instances use that interface and official model; no custom cell or changed area calculation.',
            'No HDL build, lint, simulation, synthesis, STA, perf or unit tests. The source ordering argument and preserved publication boundary need eventual relevant burst/order/backpressure/error coverage before adoption.'
        ])
    write(BASE/'A25_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':
    main()
