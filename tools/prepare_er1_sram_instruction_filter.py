"""Replace instruction-filter data FFs by banked course SRAM; no HDL runs."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A23_early_frontend_redirect'
TARGET=BASE/'A24_sram_instruction_filter'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/cache/rv32_icache_nonblocking.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer LOOP_BUFFER_LINES = 0,',
        '    parameter integer LOOP_BUFFER_LINES = 0,\n    parameter integer LOOP_BUFFER_SRAM = 0,')
    text=once(text,'.LINES(LOOP_BUFFER_LINES),.EPOCH_WIDTH(EPOCH_WIDTH)',
        '.LINES(LOOP_BUFFER_LINES),.DATA_SRAM(LOOP_BUFFER_SRAM),.EPOCH_WIDTH(EPOCH_WIDTH)')
    text=once(text,'    parameter integer LINES=16,EPOCH_WIDTH=4,',
        '    parameter integer LINES=16,EPOCH_WIDTH=4,DATA_SRAM=0,')
    text=once(text,'    wire [TAG_BITS+128-1:0] row_payload [0:LINES-1];',
        '    wire [TAG_BITS-1:0] row_tags [0:LINES-1];')
    text=once(text,'''    rv32_frequency_event_select #(.WIDTH(128),.EVENTS(LINES),.PRIORITY(0)) line_select (
        .events_i(hits),.values_i(row_lines),.write_o(),.value_o(hit_line));''','''    generate if(DATA_SRAM==0) begin:g_register_line_read
        rv32_frequency_event_select #(.WIDTH(128),.EVENTS(LINES),.PRIORITY(0)) line_select (
            .events_i(hits),.values_i(row_lines),.write_o(),.value_o(hit_line));
    end else begin:g_no_register_line_read
        assign hit_line=128'b0;
    end endgenerate''')
    text=once(text,'''    wire release_miss=primary_live && if_resp_ready_i;
    wire fast_slot_free=!fast_valid || !fast_live || if_resp_ready_i;
    wire can_start=!reset_i && (!miss_live || release_miss) && fast_slot_free;''','''    wire release_miss=primary_live && if_resp_ready_i;
    wire fill=!reset_i && primary_live && if_resp_ready_i && !primary_resp_error_i &&
        primary_resp_line_addr_i=={primary_resp_pc_i[31:4],4'b0};
    // Independent low-index banks allow a fill and next hit together. Only
    // a hit in the actual write bank waits, retaining the original old-line
    // semantics when that row is being replaced.
    localparam integer SRAM_BANKS=(LINES<4)?LINES:4;
    localparam integer SRAM_BANK_WIDTH=$clog2(SRAM_BANKS);
    localparam integer SRAM_DEPTH=LINES/SRAM_BANKS;
    localparam integer SRAM_ADDR_WIDTH=(SRAM_DEPTH<=1)?1:$clog2(SRAM_DEPTH);
    wire hit_fill_conflict=(DATA_SRAM!=0) && fill && hit &&
        (if_req_pc_i[4 +: SRAM_BANK_WIDTH]==primary_resp_line_addr_i[4 +: SRAM_BANK_WIDTH]);
    wire fast_slot_free=!fast_valid || !fast_live || if_resp_ready_i;
    wire can_start=!reset_i && (!miss_live || release_miss) && fast_slot_free && !hit_fill_conflict;''')
    text=once(text,'''    rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH+128)) fast_response (
        .clk_i(clk_i),.write_i(accept_hit),.data_i({if_req_pc_i,if_req_epoch_i,hit_line}),
        .data_o({fast_pc,fast_epoch,fast_line}));''','''    generate if(DATA_SRAM!=0) begin:g_sram_lines
        wire [SRAM_BANKS*128-1:0] bank_data;
        wire [SRAM_BANKS-1:0] response_banks;
        rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH)) fast_identity (
            .clk_i(clk_i),.write_i(accept_hit),.data_i({if_req_pc_i,if_req_epoch_i}),
            .data_o({fast_pc,fast_epoch}));
        for(genvar bank=0;bank<SRAM_BANKS;bank=bank+1) begin:g_bank
            localparam [SRAM_BANK_WIDTH-1:0] BANK=bank;
            wire bank_fill=fill && primary_resp_line_addr_i[4 +: SRAM_BANK_WIDTH]==BANK;
            wire bank_hit=accept_hit && if_req_pc_i[4 +: SRAM_BANK_WIDTH]==BANK;
            // FakeRAM invalidates rdata on idle/write edges. Reread a held
            // response on every stalled edge instead of assuming Q holds.
            // A live primary fill requires ready, so cannot overwrite a
            // backpressured fast response.
            wire bank_hold=fast_live && !fast_slot_free && fast_pc[4 +: SRAM_BANK_WIDTH]==BANK;
            wire [INDEX_WIDTH-1:0] read_index=bank_hit?
                if_req_pc_i[4 +: INDEX_WIDTH]:fast_pc[4 +: INDEX_WIDTH];
            wire [SRAM_ADDR_WIDTH-1:0] address=bank_fill?
                SRAM_ADDR_WIDTH'(primary_resp_line_addr_i[4 +: INDEX_WIDTH] >> SRAM_BANK_WIDTH):
                SRAM_ADDR_WIDTH'(read_index >> SRAM_BANK_WIDTH);
            sram_fakeram #(.DEPTH(SRAM_DEPTH),.WIDTH(128),.WRITE_GRANULARITY(16)) data (
                .clk(clk_i),.en(!reset_i && (bank_fill || bank_hit || bank_hold)),
                .we(bank_fill),.wmask(8'hff),.addr(address),
                .wdata(primary_resp_line_data_i),.rdata(bank_data[bank*128 +: 128]));
            assign response_banks[bank]=fast_live && fast_pc[4 +: SRAM_BANK_WIDTH]==BANK;
        end
        rv32_frequency_event_select #(.WIDTH(128),.EVENTS(SRAM_BANKS),.PRIORITY(0)) response_read (
            .events_i(response_banks),.values_i(bank_data),.write_o(),.value_o(fast_line));
    end else begin:g_register_lines
        rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH+128)) fast_response (
            .clk_i(clk_i),.write_i(accept_hit),.data_i({if_req_pc_i,if_req_epoch_i,hit_line}),
            .data_o({fast_pc,fast_epoch,fast_line}));
    end endgenerate''')
    # The fill predicate moved above ready arbitration, without changing it.
    old_fill='''    wire fill=!reset_i && primary_live && if_resp_ready_i && !primary_resp_error_i &&
        primary_resp_line_addr_i=={primary_resp_pc_i[31:4],4'b0};'''
    assert text.count(old_fill)==2
    tail=text.index('    rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH)) miss_identity (')
    text=text[:tail]+once(text[tail:],old_fill,'')
    text=once(text,'        wire [TAG_BITS-1:0] row_tag=row_payload[row][128 +: TAG_BITS];',
        '        wire [TAG_BITS-1:0] row_tag=row_tags[row];')
    text=once(text,'        assign row_lines[row*128 +: 128]=row_payload[row][127:0];','')
    text=once(text,'''        rv32_frequency_word_bank #(.WIDTH(TAG_BITS+128)) payload (
            .clk_i(clk_i),.write_i(row_write),
            .data_i({primary_resp_line_addr_i[31:4+INDEX_WIDTH],primary_resp_line_data_i}),
            .data_o(row_payload[row]));''','''        if(DATA_SRAM!=0) begin:g_sram_tag
            rv32_frequency_word_bank #(.WIDTH(TAG_BITS)) tag (
                .clk_i(clk_i),.write_i(row_write),
                .data_i(primary_resp_line_addr_i[31:4+INDEX_WIDTH]),.data_o(row_tags[row]));
            assign row_lines[row*128 +: 128]=128'b0;
        end else begin:g_register_payload
            wire [TAG_BITS+128-1:0] payload_word;
            rv32_frequency_word_bank #(.WIDTH(TAG_BITS+128)) payload (
                .clk_i(clk_i),.write_i(row_write),
                .data_i({primary_resp_line_addr_i[31:4+INDEX_WIDTH],primary_resp_line_data_i}),
                .data_o(payload_word));
            assign row_tags[row]=payload_word[128 +: TAG_BITS];
            assign row_lines[row*128 +: 128]=payload_word[127:0];
        end''')
    # Primary cache behavior and all filter validity/epoch state retain exact
    # parent bytes. Only the two wrapper parameter additions touch primary.
    start='    wire [CACHE_LINES-1:0] valid_bits;'
    end='module rv32_instruction_line_filter #('
    assert text[text.index(start):text.index(end)]==original[original.index(start):original.index(end)]
    state='    always @(posedge clk_i) begin\n        if(reset_i) begin fast_valid'
    assert text.split(state,1)[1]==original.split(state,1)[1]
    changes[name]=text
    for name,default in [('rtl/cpu_core.v',0),('rtl/course/student_top.v',1)]:
        text=(PARENT/name).read_text(encoding='utf-8')
        lines_default=0 if default==0 else 16
        text=once(text,f'    parameter integer ICACHE_LOOP_LINES = {lines_default},',
            f'    parameter integer ICACHE_LOOP_LINES = {lines_default},\n    parameter integer ICACHE_LOOP_SRAM = {default},')
        if default==0:
            text=once(text,'.LOOP_BUFFER_LINES(ICACHE_LOOP_LINES),',
                '.LOOP_BUFFER_LINES(ICACHE_LOOP_LINES), .LOOP_BUFFER_SRAM(ICACHE_LOOP_SRAM),')
        else:
            text=once(text,'.ICACHE_LOOP_LINES(ICACHE_LOOP_LINES),',
                '.ICACHE_LOOP_LINES(ICACHE_LOOP_LINES), .ICACHE_LOOP_SRAM(ICACHE_LOOP_SRAM),')
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
    record['parameter_overrides']=dict(parent['parameter_overrides'],ICACHE_LOOP_SRAM=1)
    record['enabled_profile']=dict(parent['enabled_profile'],ICACHE_LOOP_SRAM=1,
        instruction_filter_sram_banks=4,instruction_filter_removed_data_ff_bits=2176,
        instruction_filter_sram_bits=2048,instruction_filter_sram_area_um2=32*round(4*16*.0419904,6))
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Keep 16 instruction-filter lines and a one-edge fast hit, replacing per-line/response data FFs with four interleaved synchronous SRAM banks; reread held responses and block only fill/read bank collisions.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        instruction_filter_removed_data_ff_bits=2176,
        instruction_filter_removed_ff_area_um2=2176*.2916,
        instruction_filter_added_course_sram_area_um2=32*round(4*16*.0419904,6),
        instruction_filter_sram_lane_clock_to_q_ns=.071262+.0000167155*4+.001243254*16,
        instruction_filter_remaining_read_mux_banks=4,
        instruction_filter_fill_conflict_can_add_wait_edge=True,
        instruction_filter_new_ipc_area_frequency_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_BANKED_SRAM_FILTER_ONE_EDGE_HIT_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,
        source_arguments=[
            'Full tag bits, 16 lines, direct index, valid updates, miss identity, epoch invalidation, primary live/error predicates and response ownership are retained; primary cache body is exact parent source.',
            'Four low-index SRAM banks each store four 128-bit lines. Existing tags select hit before the edge; the bank read and fast PC/epoch capture occur on that same edge. Selected macro output is the fast response, removing the redundant 128-bit response FF.',
            'A live primary fill can write one bank while a new hit reads a different bank. A same-bank hit stalls until after the fill edge, preserving old-line replacement semantics. Miss requests can still overlap a fill.',
            'The course FakeRAM model invalidates rdata on idle/write edges. A fast response under backpressure rereads its saved PC bank/address each edge. A fill requires frontend ready, so cannot overwrite a stalled fast response.',
            'Consecutive hits and changing banks use the newly accepted identity at each edge. Idle/stale data are not published; reset and current-epoch guards are unchanged.',
            'Course SRAM model formula adds 85.996352um2 after per-macro rounding; mapped reference DFF area for 2176 removed data FFs is 634.5216um2. This is only a component comparison, not a prediction of net mapped gain; new commands/output selection have cost.',
            '16-bit write granularity creates 32 priced course macros, with modeled clock-to-Q about0.091221ns. No custom blackbox, area override, omitted SRAM area or course-library modification.',
            'No HDL build, lint, simulation, synthesis, STA, performance or unit tests were started. IPC effect of fill-bank conflicts and actual new timing/area are unmeasured. All earlier frozen candidates/runs and main EU source remain unchanged.'
        ])
    write(BASE/'A24_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':
    main()
