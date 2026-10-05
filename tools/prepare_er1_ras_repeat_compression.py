"""Compress equal adjacent return addresses; no HDL execution or claimed gain."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A63_rs_predecode_issue_cancel'
TARGET = BASE / 'A64_ras_repeat_compression'
RUN = Path('F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A64_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    case = RUN / 'source/.deps/RISC-V-CPU-2026/testcases/perf_towers'
    row = next(r for r in read(RUN/'result/ipc.json')['results'] if r['name']=='perf_towers')
    assert sha(case/'program.data') == row['program_sha256']
    words = {}
    for line in (case/'program.S').read_text(encoding='utf-8').splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+', line)
        if m:
            words[int(m[1],16)] = int(m[2],16)
    # Static disassembly identity only: no interpretation or program execution.
    image = {}; position = 0
    for line in (case/'program.data').read_text(encoding='utf-8').splitlines():
        tokens = line.split('#',1)[0].split()
        for token in tokens:
            if token.startswith('@'): position = int(token[1:],16)
            else: image[position] = int(token,16); position += 1
    for address, word in words.items():
        assert word == sum(image[address+b] << (8*b) for b in range(4)), address
    expected = {0x28:0x45c080e7, 0x4cc:0x00700593, 0x4f0:0xefc080e7,
                0x3fc:0xea430067, 0x2ec:0xfffa8a93, 0x308:0xf98080e7, 0x3e4:0x00008067}
    assert all(words[a] == word for a, word in expected.items())
    changes = {}
    name = 'rtl/cpu_core.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer FRONTEND_RAS_PREDECODE = 0,',
        '''    parameter integer FRONTEND_RAS_PREDECODE = 0,
    parameter integer RAS_REPEAT_COMPRESSION = 0,
    parameter integer RAS_REPEAT_COUNTER_BITS = 6,''')
    marker = '    // Consecutive lane PCs route to disjoint low-index predictor banks.'
    compression = '''    // Consecutive identical return addresses occupy one physical word.
    // A repetition count is the number of additional logical copies. Full
    // counts allocate another ordinary word rather than wrapping to zero.
    wire ras_repeat_push,ras_repeat_pop;
    generate if(RAS_REPEAT_COMPRESSION!=0) begin:g_ras_repeat_compression
        wire [4*RAS_REPEAT_COUNTER_BITS-1:0] repeat_rows;
        wire [RAS_REPEAT_COUNTER_BITS-1:0] top_repeats;
        rv32_frequency_array_read #(.WIDTH(RAS_REPEAT_COUNTER_BITS),.ENTRIES(4),.INDEX_WIDTH(2)) repeat_query (
            .rows_i(repeat_rows),.index_i(ras_top_index),.value_o(top_repeats));
        assign ras_repeat_push=ras_push && ras_count!=0 &&
            ras_target==ras_push_address && !(&top_repeats);
        assign ras_repeat_pop=ras_pop && top_repeats!=0;
        for(genvar repeat_row=0;repeat_row<4;repeat_row=repeat_row+1) begin:g_row
            wire [RAS_REPEAT_COUNTER_BITS-1:0] saved_repeats;
            wire allocate=!reset && ras_push && !ras_repeat_push && ras_sp==repeat_row;
            wire increment=!reset && ras_repeat_push && ras_top_index==repeat_row;
            wire decrement=!reset && ras_repeat_pop && ras_top_index==repeat_row;
            wire [RAS_REPEAT_COUNTER_BITS-1:0] next_repeats=allocate?
                {RAS_REPEAT_COUNTER_BITS{1'b0}}:
                (increment?saved_repeats+1'b1:saved_repeats-1'b1);
            rv32_frequency_word_bank #(.WIDTH(RAS_REPEAT_COUNTER_BITS)) repeat_owner (
                .clk_i(clk),.write_i(allocate || increment || decrement),
                .data_i(next_repeats),.data_o(saved_repeats));
            assign repeat_rows[repeat_row*RAS_REPEAT_COUNTER_BITS +: RAS_REPEAT_COUNTER_BITS]=saved_repeats;
        end
        initial begin
            if(RAS_REPEAT_COUNTER_BITS<1 || RAS_REPEAT_COUNTER_BITS>16)
                $fatal(1,"RAS repetition counter width must be in 1..16");
        end
    end else begin:g_no_ras_repeat_compression
        assign ras_repeat_push=1'b0;
        assign ras_repeat_pop=1'b0;
    end endgenerate

'''
    text = once(text, marker, compression + marker)
    text = once(text, '        wire write_event=!reset && ras_push && ras_sp==ras_row;',
        '        wire write_event=!reset && ras_push && !ras_repeat_push && ras_sp==ras_row;')
    text = once(text, '        else if(ras_push) begin', '        else if(ras_push && !ras_repeat_push) begin')
    text = once(text, '        end else if(ras_pop) begin', '        end else if(ras_pop && !ras_repeat_pop) begin')
    a = '    // Consecutive lane PCs route to disjoint low-index predictor banks.'
    b = '    genvar ras_row;'
    assert text[text.index(a):text.index(b)] == original[original.index(a):original.index(b)]
    a = '    rv32_fetch_frontend #'
    assert text[text.index(a):] == original[original.index(a):]
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT/name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RAS_PREDECODE = 2,',
        '''    parameter integer FRONTEND_RAS_PREDECODE = 2,
    parameter integer RAS_REPEAT_COMPRESSION = 1,
    parameter integer RAS_REPEAT_COUNTER_BITS = 6,''')
    text = once(text, '.FRONTEND_RAS_PREDECODE(FRONTEND_RAS_PREDECODE),',
        '.FRONTEND_RAS_PREDECODE(FRONTEND_RAS_PREDECODE), .RAS_REPEAT_COMPRESSION(RAS_REPEAT_COMPRESSION), .RAS_REPEAT_COUNTER_BITS(RAS_REPEAT_COUNTER_BITS),')
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},preparation_script_sha256=sha(Path(__file__)),
        tests_started=False,adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],RAS_REPEAT_COMPRESSION=1,RAS_REPEAT_COUNTER_BITS=6)
    record['enabled_profile'] = dict(parent['enabled_profile'],ras_repeat_compression=True,ras_physical_entries=4,
        ras_repeat_counter_bits=6,ras_repeat_added_ff_bits=24,ras_repeat_added_address_bits=0,
        ras_repeat_added_sram_bits=0,ras_repeat_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Compress equal adjacent RAS return addresses with a per-word repetition count. A same-address call increments a non-full top counter; a return decrements a nonzero counter without changing the physical pointer/count. New/different/full-counter pushes retain the existing circular four-word allocation, initialize repeat count zero and hold all prediction/prefix/ISA/recovery interfaces.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        towers_static_direct_recursion_depth=7,towers_static_identical_recursive_return_pc='0x0000030c',
        towers_ideal_max_logical_call_depth=8,towers_ideal_compressed_physical_groups=3,
        ras_repeat_actual_ipc_area_frequency_unknown=True,
        ras_repeat_limitation='BTB can already predict common recursive return targets after RAS underflow; unrepaired wrong-path stack changes remain. Capacity improvement is not evidence of a large IPC gain.')
    write(TARGET/'candidate.json',record)
    proof = dict(status='SOURCE_RAS_REPEAT_COMPRESSION_UNTESTED',candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        changed_files=list(changes),tests_started=False,adopted=False,added_ff_bits=24,added_sram_bits=0,
        added_pipeline_edges=0,physical_address_words_unchanged=4,
        static_program_evidence=dict(run=str(RUN),program_sha256=sha(case/'program.data'),disassembly_sha256=sha(case/'program.S'),
            disassembly_words_bound_to_image=len(words),selected_words={f'0x{a:08x}':f'0x{w:08x}' for a,w in expected.items()},
            logical_depth_inference='Main initializes seven disks, then passes that count through towers_solve, which tail-jumps without a push. The helper decrements n until1 and recursively calls from0x308, returning to0x30c six times. Including _start/main and main/solve calls, the ideal path needs8 logical addresses but3 compressed groups; the recursive repeat counter reaches5.'),
        research_references=[dict(url='https://raw.githubusercontent.com/OpenXiangShan/XiangShan/kunminghu/src/main/scala/xiangshan/frontend/RAS.scala',
            scope='Historical commented RAS reference block demonstrates same-return-address counters, new physical allocation on counter saturation and separate recovery. No code imported and no claim that this is the current active XiangShan RAS.'),
            dict(url='https://www.cs.princeton.edu/research/techreps/290',scope='Primary research identifies wrong-path RAS corruption and top pointer/content repair. Its measured gains are not transferred to this CPU.')],
        source_arguments=[
            'Expanding each physical entry {address,repeats} into repeats+1 identical logical return addresses gives ordinary LIFO behavior until physical circular overflow. Equal non-full top pushes extend the last run; nonzero-counter pops remove one logical copy; zero-counter pops remove the physical run. Counter saturation allocates a new run instead of wrapping.',
            'Existing32-bit return-address query, return-hit qualification, accepted response/call/return prefix, first-event lane ordering, original four payload words and all frontend/backend/cache ownership are unchanged. Compression changes speculative prediction capacity, never the architectural return address source or JALR execution.',
            'Repetition words are unreset like existing address words. Any physical push initializes its counter0, and count0 after reset makes all old words unobservable. Legal repeated push/pop modifies only the selected top word. All counter arithmetic uses local saved words before the late write control.',
            'Core default0 elaborates no repetition state and reduces payload writes and pointer/count transitions to the original behavior. Course top1/BITS6 adds exactly4x6=24 logical state bits; no address/SRAM/checkpoint/epoch/ROB-tag state and no pipeline edge.',
            'This is source reasoning and static source/image evidence only. New full-address equality and counter controls may add a frontend critical path. Area, frequency and IPC are unknown; existing BTB underflow assistance may make capacity-only IPC gains small, and wrong-path corruption still needs explicit handling.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Future meaningful batch coverage includes mixed/repeated calls and returns, counter saturation/chunk allocation, physical overflow/underflow, stall/response prefix, reset and redirect, all FE widths, compression0 and counter widths, official six IPC and full RV32IM correctness before adoption.'
        ])
    write(BASE/'A64_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__=='__main__':
    main()
