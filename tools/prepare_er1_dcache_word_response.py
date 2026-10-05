"""Narrow OoO cache waiter/held CPU responses while preserving cache lines."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A35_alloc_ready_store_data'
TARGET=BASE/'A36_dcache_word_response'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/cache/rv32_dcache_nonblocking.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer HIT_BYPASS = 1,',
        '    parameter integer HIT_BYPASS = 1,\n    parameter integer WORD_RESPONSE = 0,')
    text=once(text,'    wire [127:0] waiter_line [0:WAITER_ENTRIES-1];',
        '    localparam integer WAITER_DATA_WIDTH=(WORD_RESPONSE!=0)?32:128;\n    wire [WAITER_DATA_WIDTH-1:0] waiter_line [0:WAITER_ENTRIES-1];')
    text=once(text,'    localparam integer WAITER_READ_WIDTH=TAG_WIDTH+167;',
        '    localparam integer WAITER_READ_WIDTH=TAG_WIDTH+39+WAITER_DATA_WIDTH;')
    for kind in ['load','store']:
        text=once(text,f'    wire [127:0] query_waiter_{kind}_waiter_line;',
            f'    wire [WAITER_DATA_WIDTH-1:0] query_waiter_{kind}_waiter_line;')
    text=once(text,'''            assign dcache_resp_line_data_o[response_word*16 +: 16]=(bypass || deferred)?
                data_rdata[response_word*16 +: 16]:resp_line_reg[response_word*16 +: 16];''','''            assign dcache_resp_line_data_o[response_word*16 +: 16]=(WORD_RESPONSE!=0)?16'b0:
                ((bypass || deferred)?data_rdata[response_word*16 +: 16]:resp_line_reg[response_word*16 +: 16]);''')
    text=once(text,'    assign dcache_resp_line_valid_o=response_output_views[2*(RESPONSE_OUTPUT_WORDS-1)] || resp_line_valid_reg;',
        '    assign dcache_resp_line_valid_o=(WORD_RESPONSE==0) && (response_output_views[2*(RESPONSE_OUTPUT_WORDS-1)] || resp_line_valid_reg);')
    # Word mode sends raw relative bytes. LSQ overlays forwarded bytes before
    # applying size/sign, including partial-forwarding cases.
    for old in ['.size_i(core_req_size),.unsigned_i(core_req_unsigned),.value_o(response_hit_word)',
                '.size_i(resp_size_reg),.unsigned_i(resp_unsigned_reg),.value_o(response_deferred_word)',
                '.size_i(query_response_mshr_size),.unsigned_i(query_response_mshr_unsigned),.value_o(response_memory_word)',
                '.size_i(core_req_size),.unsigned_i(core_req_unsigned),.value_o(response_forward_word)']:
        size,unsigned=old.split('.size_i(',1)[1].split(')',1)[0],old.split('.unsigned_i(',1)[1].split(')',1)[0]
        text=once(text,old,old.replace(f'.size_i({size})',f'.size_i((WORD_RESPONSE!=0)?2\'d2:{size})').replace(
            f'.unsigned_i({unsigned})',f'.unsigned_i((WORD_RESPONSE!=0)?1\'b1:{unsigned})'))
    old='''        rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2)) line_selector (
            .events_i({response_fill && !waiter_store[waiter_row],local_fill && !waiter_store[waiter_row]}),
            .values_i({response_line,query_local_mshr_wdata}),
            .write_o(line_write),.value_o(line_next));
        rv32_frequency_word_bank #(.WIDTH(128)) line_owner (
            .clk_i(clk_i),.write_i(line_write),.data_i(line_next),.data_o(waiter_line[waiter_row]));'''
    new='''        if(WORD_RESPONSE!=0) begin:g_word_waiter
            // Natural LB/LH/LW alignment never crosses an aligned word.
            // Choose that word before capture, and shift its low byte index
            // only after the original waiter selection. This avoids a full
            // four-bit line shifter for each waiter.
            wire [31:0] response_word_data,local_word_data,word_next;
            rv32_frequency_line_extract32 response_word_extract (
                .line_i(response_line),.offset_i({waiter_addr[waiter_row][3:2],2'b0}),
                .size_i(2'd2),.unsigned_i(1'b1),.value_o(response_word_data));
            rv32_frequency_line_extract32 local_word_extract (
                .line_i(query_local_mshr_wdata),.offset_i({waiter_addr[waiter_row][3:2],2'b0}),
                .size_i(2'd2),.unsigned_i(1'b1),.value_o(local_word_data));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2)) word_selector (
                .events_i({response_fill && !waiter_store[waiter_row],local_fill && !waiter_store[waiter_row]}),
                .values_i({response_word_data,local_word_data}),.write_o(line_write),.value_o(word_next));
            rv32_frequency_word_bank #(.WIDTH(32)) word_owner (
                .clk_i(clk_i),.write_i(line_write),.data_i(word_next),.data_o(waiter_line[waiter_row]));
            assign line_next=0;
        end else begin:g_line_waiter
            rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2)) line_selector (
                .events_i({response_fill && !waiter_store[waiter_row],local_fill && !waiter_store[waiter_row]}),
                .values_i({response_line,query_local_mshr_wdata}),
                .write_o(line_write),.value_o(line_next));
            rv32_frequency_word_bank #(.WIDTH(128)) line_owner (
                .clk_i(clk_i),.write_i(line_write),.data_i(line_next),.data_o(waiter_line[waiter_row]));
        end'''
    text=once(text,old,new)
    text=once(text,'''    rv32_frequency_line_extract32 waiter_extract (
        .line_i(query_waiter_load_waiter_line),.offset_i(query_waiter_load_waiter_addr[3:0]),
        .size_i(query_waiter_load_waiter_size),.unsigned_i(query_waiter_load_waiter_unsigned),.value_o(response_waiter_word));''','''    generate if(WORD_RESPONSE!=0) begin:g_word_waiter_extract
        rv32_frequency_line_extract32 waiter_extract (
            .line_i({96'b0,query_waiter_load_waiter_line}),.offset_i({2'b0,query_waiter_load_waiter_addr[1:0]}),
            .size_i(2'd2),.unsigned_i(1'b1),.value_o(response_waiter_word));
    end else begin:g_line_waiter_extract
        rv32_frequency_line_extract32 waiter_extract (
            .line_i(query_waiter_load_waiter_line),.offset_i(query_waiter_load_waiter_addr[3:0]),
            .size_i(query_waiter_load_waiter_size),.unsigned_i(query_waiter_load_waiter_unsigned),.value_o(response_waiter_word));
    end endgenerate''')
    begin=text.index('    wire [159:0] response_data_next,response_data_saved;')
    end=text.index('    // This metadata is read only',begin)
    oldblock=text[begin:end]
    legacy=oldblock.replace('    wire response_sram_capture=!reset_i && resp_from_sram && resp_valid_reg;\n','')
    newblock='''    wire response_sram_capture=!reset_i && resp_from_sram && resp_valid_reg;
    generate if(WORD_RESPONSE!=0) begin:g_word_response_owner
        wire [31:0] response_word_next;
        rv32_frequency_event_select #(.WIDTH(32),.EVENTS(6)) response_word_selector (
            .events_i({response_demand_capture,response_failed_load,response_waiter_capture,response_forward_capture,
                       response_hit_capture && TAG_SRAM!=0,response_sram_capture}),
            .values_i({response_memory_word,32'b0,response_waiter_word,response_forward_word,
                       response_hit_word,response_deferred_word}),
            .write_o(response_data_write),.value_o(response_word_next));
        rv32_frequency_word_bank #(.WIDTH(32)) response_word_owner (
            .clk_i(clk_i),.write_i(response_data_write),.data_i(response_word_next),.data_o(resp_word_reg));
        assign resp_line_reg=128'b0;
    end else begin:g_line_response_owner
'''+legacy+'''    end endgenerate
'''
    text=text[:begin]+newblock+text[end:]
    # None of these substitutions touches an always process. Record their
    # exact text, up to the next module declaration or top-level generate.
    import re
    def clocked_chunks(s):
        return re.findall(r'    always @\(posedge clk_i\).*?(?=\n    (?:always |endgenerate|generate |wire |localparam |endmodule)|\Z)',s,re.S)
    assert clocked_chunks(text)==clocked_chunks(original)
    changes[name]=text
    for name in ['rtl/cpu_core.v','rtl/course/student_top.v']:
        original=(PARENT/name).read_text(encoding='utf-8')
        anchor=('    parameter integer DCACHE_MSHRS = ' if name.endswith('student_top.v')
                else '    parameter integer DCACHE_LINES = ')
        assert original.count(anchor)==1
        offset=original.index('\n',original.index(anchor))
        default=1 if name.endswith('student_top.v') else 0
        text=original[:offset]+f'\n    parameter integer DCACHE_WORD_RESPONSE = {default},'+original[offset:]
        if name.endswith('student_top.v'):
            text=once(text,'.DCACHE_LINES(DCACHE_LINES),',
                '.DCACHE_LINES(DCACHE_LINES), .DCACHE_WORD_RESPONSE(DCACHE_WORD_RESPONSE),')
        else:
            text=once(text,'rv32_dcache_nonblocking #(.HIT_BYPASS(1),',
                'rv32_dcache_nonblocking #(.WORD_RESPONSE((DCACHE_WORD_RESPONSE!=0) && (SERIAL_BACKEND==0)), .HIT_BYPASS(1),')
        changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],DCACHE_WORD_RESPONSE=1)
    record['enabled_profile']=dict(parent['enabled_profile'],DCACHE_WORD_RESPONSE=1,
        dcache_waiter_payload_bits=32,dcache_held_cpu_response_bits=32,
        dcache_word_response_removed_ff_bits_at_waiters8=896,
        dcache_full_line_sram_mshr_victim_store_payload_retained=True)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'OoO D-cache CPU response uses raw relative 32-bit bytes and line_valid=0. Each waiter stores one aligned requested word; final byte shift occurs after waiter selection. Held CPU data owner shrinks160 to32 bits. Full128-bit cache SRAM/refill/victim/MSHR/store buses remain unchanged.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        dcache_waiter_removed_ff_bits_at_waiters8=768,dcache_held_response_removed_ff_bits=128,
        dcache_word_response_removed_ff_area_component_um2=896*.2916,
        dcache_response_lsq_full_line_extract_removed_in_active_profile=True,
        dcache_word_response_added_pipeline_edges=0,
        dcache_word_response_actual_ppa_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_WORD_CACHE_RESPONSE_WAITER_PROJECTION_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),
        removed_ff_bits_at_waiters8=896,ff_area_component_um2=896*.2916,
        added_sram_bits=0,added_pipeline_edges=0,clocked_process_chunks_exact=True,tests_started=False,adopted=False,
        source_arguments=[
            'Course requirements guarantee naturally aligned byte/halfword/word loads. Select the aligned32-bit word with address[3:2] before each original waiter capture; shift address[1:0] after original ready-waiter selection. Every required load byte lies within this stored word.',
            'Word response mode sends raw bytes, size2 unsigned1 in cache extraction; LSQ originally supports line_valid=0, merges access-relative youngest-store forwarded bytes, then performs its original size/sign format. B/H sign handling occurs after forwarding, preserving partial forwards.',
            'Immediate hit, deferred SRAM hit, demand-memory return, MSHR-forward hit, waiter response and failure events preserve original selection priority, full LSQ identity/address/error, response readiness/hold/lifetime and all clocked valid/control processes.',
            'WORD_RESPONSE defaults0; cache legacy full-line response remains under explicit generate fallback. Core activates word mode only for OoO backend with a nonblocking cache; serial and blocking-cache paths keep old interfaces.',
            'Cache SRAM128-bit lines, capacity/associativity, MSHR line write masks/store data, merged store fill, dirty victim data and writeback/AXI payloads are unchanged. This projection applies only to CPU-facing retained data, never cache storage or external line transfer.',
            'With eight waiters,128-to32 removes768 data FF bits. The held CPU response owner160-to32 removes another128, total896 bits, FF component261.2736um2. Line metadata pruning/holding/readmux savings are not counted; added per-row aligned-word extraction and control costs require new mapping.',
            'Raw32 responses make LSQ full128-bit return-window extraction unused in the active profile. This moves per-waiter line selection before its existing register and narrows response selection; no extra pipeline edge or completion producer is added. Actual timing may still be constrained by cache hit extraction or bus-to-waiter capture.',
            'This is an explicit supported-interface projection, not equality of cache diagnostic full-line outputs. No HDL build, lint, simulation, synthesis, STA, CPU/perf or unit tests.',
            'Later meaningful coverage needs every naturally aligned byte/halfword/word offset, signed extremes, partial LSQ forwarding, different waiter words/offsets on one miss, store-merged response/local fills, SRAM hit hold, error returns and wrong-path/recycled LSQ responses.'
        ])
    write(BASE/'A36_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','removed_ff_bits_at_waiters8','tests_started')})


if __name__=='__main__':main()
