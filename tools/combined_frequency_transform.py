"""Combine frequency strategies before one final native/PPA validation run.

Uses the frozen eight-stage CPU, preserves the course measurement flow, and
retains functional storage in every new hierarchy boundary.
"""
from pathlib import Path
import hashlib
import json
import re
from prepare_rs_age_cpu_integration import adapt as adapt_age
from prepare_rob_mmio_cpu_integration import adapt as adapt_mmio


def replace(s, old, new):
    assert s.count(old)==1, (old,s.count(old))
    return s.replace(old,new)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


DCACHE_WORD = r'''
// Owns one real SRAM word lane and decodes competing commands locally.
// Store-hit addresses never traverse the unrelated victim-way selection.
(* keep_hierarchy = 1 *)
module rv32_dcache_command_word #(
    parameter integer SETS=512, WAYS=2, WAY=0,
    parameter integer IW=$clog2(SETS), EW=$clog2(SETS*WAYS)
) (
    input wire clk_i, reset_i,
    input wire refill_i, local_i, store_i, input_read_i, deferred_read_i,
    input wire [EW-1:0] refill_entry_i, local_entry_i, hit_entry_i,
    input wire [IW-1:0] input_index_i, deferred_index_i,
    input wire [31:0] response_data_i, response_store_data_i,
    input wire response_store_i,
    input wire [3:0] response_mask_i,
    input wire [31:0] local_data_i, store_data_i,
    input wire [3:0] store_mask_i,
    output wire [31:0] data_o
);
    wire refill_way = refill_i && ((refill_entry_i % WAYS)==WAY);
    wire local_way = !refill_i && local_i && ((local_entry_i % WAYS)==WAY);
    wire store_way = !refill_i && !local_i && store_i && ((hit_entry_i % WAYS)==WAY);
    wire writing = refill_way || local_way || store_way;
    wire [IW-1:0] address = refill_way ? refill_entry_i/WAYS :
        local_way ? local_entry_i/WAYS : store_way ? hit_entry_i/WAYS :
        deferred_read_i ? deferred_index_i : input_index_i;
    wire [3:0] mask = (refill_way || local_way) ? 4'hf : store_mask_i;
    wire [31:0] refill_data;
    genvar byte_id;
    generate for(byte_id=0;byte_id<4;byte_id=byte_id+1) begin:g_merge
        assign refill_data[byte_id*8 +: 8] = response_store_i && response_mask_i[byte_id] ?
            response_store_data_i[byte_id*8 +: 8] : response_data_i[byte_id*8 +: 8];
    end endgenerate
    wire [31:0] write_data = refill_way ? refill_data : local_way ? local_data_i : store_data_i;
    sram_fakeram #(.DEPTH(SETS),.WIDTH(32),.WRITE_GRANULARITY(8)) storage (
        .clk(clk_i),.en(!reset_i && (writing || input_read_i || deferred_read_i)),
        .we(writing),.wmask(mask),.addr(address),.wdata(write_data),.rdata(data_o));
endmodule
'''


DECODE_RING = r'''
// Ordered elastic bundle implemented as a ring: dequeue changes a pointer,
// never shifts the entire decoded payload through a recovery/ready mux.
module rv32_decode_bundle_register #(
    parameter integer LANES=4, PAYLOAD_WIDTH=194,
    parameter integer CW=(LANES<2)?1:$clog2(LANES+1),
    parameter integer PW=(LANES<2)?1:$clog2(LANES)
) (
    input wire clk_i,reset_i,flush_i,
    input wire [LANES-1:0] valid_i,
    output reg [LANES-1:0] ready_o,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    output reg [LANES-1:0] valid_o,
    input wire [LANES-1:0] ready_i,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o
);
    localparam integer WORDS=(PAYLOAD_WIDTH+31)/32;
    reg [CW-1:0] count;
    reg [PW-1:0] head,tail;
    reg [CW-1:0] consumed,accepted;
    integer lane,capacity;
    reg prefix;
    wire [LANES-1:0] push = valid_i & ready_o;
    wire [LANES*PAYLOAD_WIDTH-1:0] rows;
    always @* begin
        consumed=0;accepted=0;valid_o=0;ready_o=0;prefix=1;
        for(lane=0;lane<LANES;lane=lane+1) begin
            valid_o[lane]=(lane<count) && !reset_i && !flush_i;
            if(prefix && valid_o[lane] && ready_i[lane]) consumed=consumed+1'b1;
            else prefix=0;
        end
        capacity=LANES-count+consumed;
        prefix=1;
        for(lane=0;lane<LANES;lane=lane+1) begin
            ready_o[lane]=prefix && (lane<capacity) && !reset_i && !flush_i;
            if(ready_o[lane] && valid_i[lane]) accepted=accepted+1'b1;
            else prefix=0;
        end
    end
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin count<=0;head<=0;tail<=0;end
        else begin
            count<=count-consumed+accepted;
            head<=(head+consumed)%LANES;
            tail<=(tail+accepted)%LANES;
        end
    end
    genvar slot,word_id,read_lane;
    generate for(slot=0;slot<LANES;slot=slot+1) begin:g_slot
        for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_field
            localparam integer W=((PAYLOAD_WIDTH-word_id*32)<32)?(PAYLOAD_WIDTH-word_id*32):32;
            wire [LANES*W-1:0] inputs;
            for(genvar writer=0;writer<LANES;writer=writer+1) begin:g_input
                assign inputs[writer*W +: W]=data_i[writer*PAYLOAD_WIDTH+word_id*32 +: W];
            end
            rv32_decode_field_bank #(.LANES(LANES),.WIDTH(W),.ROW(slot),.PW(PW)) bank (
                .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),.tail_i(tail),
                .push_i(push),.data_i(inputs),.data_o(rows[slot*PAYLOAD_WIDTH+word_id*32 +: W]));
        end
    end
    for(read_lane=0;read_lane<LANES;read_lane=read_lane+1) begin:g_read
        assign data_o[read_lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]=
            rows[((head+read_lane)%LANES)*PAYLOAD_WIDTH +: PAYLOAD_WIDTH];
    end endgenerate
endmodule

// Functional state owner, not a buffer-only hierarchy boundary.
(* keep_hierarchy = 1 *)
module rv32_decode_field_bank #(
    parameter integer LANES=4,WIDTH=32,ROW=0,PW=(LANES<2)?1:$clog2(LANES)
) (
    input wire clk_i,reset_i,flush_i,
    input wire [PW-1:0] tail_i,
    input wire [LANES-1:0] push_i,
    input wire [LANES*WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
    wire [LANES-1:0] selected;
    genvar writer;
    generate for(writer=0;writer<LANES;writer=writer+1) begin:g_select
        assign selected[writer]=push_i[writer] && (((tail_i+writer)%LANES)==ROW);
    end endgenerate
    reg [WIDTH-1:0] next_data;
    integer lane;
    always @* begin
        next_data=0;
        for(lane=0;lane<LANES;lane=lane+1)
            next_data=next_data | ({WIDTH{selected[lane]}} & data_i[lane*WIDTH +: WIDTH]);
    end
    always @(posedge clk_i) begin
        if(reset_i) data_o<=0;
        else if(!flush_i && (|selected)) data_o<=next_data;
    end
endmodule
'''


def transform(root):
    root=Path(root)
    origins={}
    def import_file(candidate,name):
        p=Path('F:/CPU2026Candidates')/candidate/name
        manifest=json.loads((p.parents[len(Path(name).parts)-1]/'candidate_manifest.json').read_text())
        assert sha(p)==manifest['files_sha256'][name]
        origins[str(p)]=sha(p)
        return p.read_text(encoding='utf-8')
    # Existing eight-stage transaction boundaries remain enabled by the profile.
    for name in ('rtl/cpu_core.v','rtl/course/student_top.v','rtl/backend/rv32_backend_joint.v'):
        p=root/name
        s=adapt_mmio(name,adapt_age(name,p.read_text(encoding='utf-8')))
        p.write_text(s,encoding='utf-8',newline='\n')
    p=root/'rtl/cpu_core.v';s=p.read_text(encoding='utf-8')
    from pipeline8_transform import DECODE_REGISTER
    s=replace(s,DECODE_REGISTER,DECODE_RING)
    p.write_text(s,encoding='utf-8',newline='\n')
    name='rtl/backend/rv32_rob.v'
    (root/name).write_text(import_file('rob_mmio_predecode_v2_20261003',name),encoding='utf-8',newline='\n')
    # ROB capacities are already required to be powers of two. Modular ages
    # need slot-width subtractors, not signed 32-bit subtract/add-back chains.
    for name,width,names in (
        ('rtl/backend/rv32_backend_joint.v','ROB_SLOT_WIDTH',
         ('recovery_rat_branch_age','recovery_rs_age','recovery_rs_branch_age',
          'recovery_completion_age','recovery_completion_branch_age',
          'producer_recovery_age','producer_recovery_branch_age',
          'alu_recovery_age','alu_recovery_branch_age')),
        ('rtl/backend/rv32_rob.v','SLOT_WIDTH',('age','younger_age','update_completion_age'))):
        p=root/name;s=p.read_text(encoding='utf-8')
        for age in names:
            s=replace(s,'    integer '+age+';',f'    reg [{width}-1:0] {age};')
            pattern=r'\s*if \('+age+r' < 0\)\s*'+age+r' = '+age+r' \+ ROB_ENTRIES;'
            s,n=re.subn(pattern,'',s)
            assert n==1,(name,age,n)
        p.write_text(s,encoding='utf-8',newline='\n')
    name='rtl/cache/rv32_icache_nonblocking.v'
    old=(root/name).read_bytes()
    assert old==(Path('F:/CPU2026Candidates/icache_static_mshr_20261003/baseline/rv32_icache_nonblocking.v')).read_bytes()
    (root/name).write_text(import_file('icache_mshr_state_banks_20261003',name),encoding='utf-8',newline='\n')

    name='rtl/frontend/rv32_fetch_frontend.v'
    s=import_file('frontend_packed_banks_20261003',name)
    # Retain both subsequent frontend fixes when importing the packed queue.
    s=replace(s,'    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,',
        '    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,\n    parameter integer NARROW_OCCUPANCY = 0, LEGACY_SENTINEL_HALT = 0,')
    s=replace(s,'    integer count_reg;', '''    localparam integer COUNT_WIDTH = (NARROW_OCCUPANCY != 0) ?
        ((FQ_DEPTH <= 1) ? 1 : $clog2(FQ_DEPTH + 1)) : 32;
    reg [COUNT_WIDTH-1:0] count_storage_reg;
    wire signed [31:0] count_reg = {{(32-COUNT_WIDTH){1'b0}}, count_storage_reg};''')
    assert s.count('count_reg <=')==3
    s=s.replace('count_reg <=','count_storage_reg <=')
    s=replace(s,"if ((if_resp_line_data_i >> ((word_index+b)*32)) == 32'h0ff00513) begin", "if ((LEGACY_SENTINEL_HALT != 0) &&\n                    ((if_resp_line_data_i >> ((word_index+b)*32)) == 32'h0ff00513)) begin")
    (root/name).write_text(s,encoding='utf-8',newline='\n')

    new_params=('ICACHE_MSHR_STATIC_WRITES','ICACHE_MSHR_STATE_BANKS','FRONTEND_QUEUE_PAYLOAD_BANKS','DCACHE_LOCAL_SRAM_COMMANDS')
    for name in ('rtl/course/student_top.v','rtl/cpu_core.v'):
        p=root/name;s=p.read_text(encoding='utf-8')
        anchor='    parameter integer DECODE_PIPELINE = 0, ISSUE_PIPELINE = 0,'
        s=replace(s,anchor,anchor+'\n'+''.join('    parameter integer '+n+' = 0,\n' for n in new_params).rstrip())
        if name.endswith('student_top.v'):
            s=replace(s,'cpu_core #(', 'cpu_core #('+''.join('.'+n+'('+n+'), ' for n in new_params))
        else:
            s=replace(s,'rv32_icache_nonblocking #(', 'rv32_icache_nonblocking #(.MSHR_STATIC_WRITES(ICACHE_MSHR_STATIC_WRITES), .MSHR_STATE_BANKS(ICACHE_MSHR_STATE_BANKS), ')
            s=replace(s,'rv32_fetch_frontend #(', 'rv32_fetch_frontend #(.QUEUE_PAYLOAD_BANKS(FRONTEND_QUEUE_PAYLOAD_BANKS), ')
            s=replace(s,'rv32_dcache_nonblocking #(', 'rv32_dcache_nonblocking #(.LOCAL_SRAM_COMMANDS(DCACHE_LOCAL_SRAM_COMMANDS), ')
        p.write_text(s,encoding='utf-8',newline='\n')
    p=root/'rtl/cache/rv32_dcache_nonblocking.v';s=p.read_text(encoding='utf-8')
    s=replace(s,'module rv32_dcache_nonblocking #(\n','module rv32_dcache_nonblocking #(\n    parameter integer LOCAL_SRAM_COMMANDS = 0,\n')
    start=s.index('            wire write_way = data_we &&')
    end=s.index('\n        end\n        sram_fakeram',start)
    original=s[start:end]
    local='''            if (LOCAL_SRAM_COMMANDS != 0) begin:g_local_commands
                for (genvar word_lane=0;word_lane<4;word_lane=word_lane+1) begin:g_word
                    rv32_dcache_command_word #(.SETS(CACHE_SETS),.WAYS(CACHE_WAYS),
                        .WAY(tag_way),.IW(CACHE_INDEX_WIDTH),.EW(CACHE_ENTRY_WIDTH)) port_bank (
                        .clk_i(clk_i),.reset_i(reset_i),
                        .refill_i(refill_array_write),.local_i(local_array_write),
                        .store_i(request_fire && request_is_store && request_hit),
                        .input_read_i(input_data_read),.deferred_read_i(deferred_data_read),
                        .refill_entry_i(mshr_victim_entry[response_index]),
                        .local_entry_i(mshr_victim_entry[local_fill_index]),.hit_entry_i(request_hit_entry),
                        .input_index_i(cache_index(dcache_req_addr_i)),.deferred_index_i(core_request_index),
                        .response_data_i(mem_resp_data_i[word_lane*32 +: 32]),
                        .response_store_i(mshr_store[response_index]),
                        .response_store_data_i(mshr_wdata[response_index][word_lane*32 +: 32]),
                        .response_mask_i(mshr_mask[response_index][word_lane*4 +: 4]),
                        .local_data_i(mshr_wdata[local_fill_index][word_lane*32 +: 32]),
                        .store_data_i(core_req_wdata[word_lane*32 +: 32]),
                        .store_mask_i(core_req_mask[word_lane*4 +: 4]),
                        .data_o(bank_rdata[tag_way*128+word_lane*32 +: 32]));
                end
            end else begin:g_original_port
'''+original+'\n            end'
    s=s[:start]+local+s[end:]
    # Declare parent-scope command signals before the generate block. Icarus
    # otherwise creates a one-bit implicit net for a forward port reference.
    s=replace(s,'    reg request_hit;\n','')
    s=replace(s,'    reg [CACHE_ENTRY_WIDTH-1:0] request_hit_entry;\n','')
    s=replace(s,'    wire request_fire =','    assign request_fire =')
    s=replace(s,'    wire request_is_store =','    assign request_is_store =')
    s=replace(s,'    genvar tag_way;', '''    reg request_hit;
    reg [CACHE_ENTRY_WIDTH-1:0] request_hit_entry;
    wire request_fire, request_is_store;
    genvar tag_way;''')
    p.write_text(s+DCACHE_WORD,encoding='utf-8',newline='\n')
    return origins


PARAMETERS=dict(DECODE_PIPELINE=1,ISSUE_PIPELINE=1,RS_AGE_WIDTH=8,
    ROB_MMIO_PREDECODE=1,ICACHE_MSHR_STATIC_WRITES=1,ICACHE_MSHR_STATE_BANKS=1,
    FRONTEND_QUEUE_PAYLOAD_BANKS=1,DCACHE_LOCAL_SRAM_COMMANDS=1)
