"""EI child: direct response-row payload selection and predecoded byte routing."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def lsq(text):
    text=change(text,'    parameter integer REQUEST_PIPELINE = 0,', '''    parameter integer REQUEST_PIPELINE = 0,
    // Decode each saved byte offset before late response-row selection and
    // route query payload from the original complete response match events.
    parameter integer RESPONSE_QUERY_PREDECODE = 0,''')
    text=change(text,'''    localparam integer RESPONSE_QUERY_WIDTH=ROB_TAG_WIDTH+43;
    wire [LSQ_ENTRIES*RESPONSE_QUERY_WIDTH-1:0] response_query_rows;
    wire [3:0] response_query_offset,response_query_mask;''', '''    localparam integer RESPONSE_OFFSET_WIDTH=(RESPONSE_QUERY_PREDECODE!=0)?16:4;
    localparam integer RESPONSE_QUERY_WIDTH=ROB_TAG_WIDTH+39+RESPONSE_OFFSET_WIDTH;
    wire [LSQ_ENTRIES*RESPONSE_QUERY_WIDTH-1:0] response_query_rows;
    wire [RESPONSE_OFFSET_WIDTH-1:0] response_query_offset;
    wire [3:0] response_query_mask;''')
    old='''    rv32_frequency_array_read #(.WIDTH(RESPONSE_QUERY_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) response_query_read (
        .rows_i(response_query_rows),.index_i(response_slot[SLOT_WIDTH-1:0]),
        .value_o({response_query_rob_tag,response_query_offset,response_query_forward,
                  response_query_mask,response_query_size,response_query_unsigned}));
    generate for(genvar response_row=0;response_row<LSQ_ENTRIES;response_row=response_row+1) begin:g_response_query
        assign response_query_rows[response_row*RESPONSE_QUERY_WIDTH +: RESPONSE_QUERY_WIDTH]={
            rob_tag_mem[response_row],addr_mem[response_row][3:0],forward_data_mem[response_row],
            forward_mask_mem[response_row],size_mem[response_row],unsigned_mem[response_row]};
    end endgenerate'''
    new='''    wire [RESPONSE_QUERY_WIDTH-1:0] response_query_packet;
    assign {response_query_rob_tag,response_query_offset,response_query_forward,
            response_query_mask,response_query_size,response_query_unsigned}=response_query_packet;
    generate if(RESPONSE_QUERY_PREDECODE!=0) begin:g_direct_response_query
        wire [LSQ_ENTRIES-1:0] matches,events;
        for(genvar query_row=0;query_row<LSQ_ENTRIES;query_row=query_row+1) begin:g_match
            // Identical predicate to the original scalar response-slot walk.
            // No generation, validity or response-wait authority is omitted.
            assign matches[query_row]=dcache_resp_valid_i &&
                tag_matches_slot(dcache_resp_lsq_tag_i,query_row) && response_wait_mem[query_row];
            if(query_row==0) begin:g_default_row
                // The old scalar walk initializes response_slot to row zero.
                assign events[query_row]=matches[query_row] || !(|matches);
            end else begin:g_other_row
                assign events[query_row]=matches[query_row];
            end
        end
        // Highest matching row wins, even for inconsistent duplicate matches.
        rv32_frequency_event_select #(.WIDTH(RESPONSE_QUERY_WIDTH),.EVENTS(LSQ_ENTRIES),.PRIORITY(1)) response_query_read (
            .events_i(events),.values_i(response_query_rows),.write_o(),.value_o(response_query_packet));
    end else begin:g_original_response_query
        rv32_frequency_array_read #(.WIDTH(RESPONSE_QUERY_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) response_query_read (
            .rows_i(response_query_rows),.index_i(response_slot[SLOT_WIDTH-1:0]),.value_o(response_query_packet));
    end endgenerate
    generate for(genvar response_row=0;response_row<LSQ_ENTRIES;response_row=response_row+1) begin:g_response_query
        wire [RESPONSE_OFFSET_WIDTH-1:0] offset_code;
        if(RESPONSE_QUERY_PREDECODE!=0) begin:g_offset_onehot
            for(genvar byte_offset=0;byte_offset<16;byte_offset=byte_offset+1) begin:g_byte
                assign offset_code[byte_offset]=(addr_mem[response_row][3:0]==byte_offset);
            end
        end else begin:g_offset_binary
            assign offset_code=addr_mem[response_row][3:0];
        end
        assign response_query_rows[response_row*RESPONSE_QUERY_WIDTH +: RESPONSE_QUERY_WIDTH]={
            rob_tag_mem[response_row],offset_code,forward_data_mem[response_row],
            forward_mask_mem[response_row],size_mem[response_row],unsigned_mem[response_row]};
    end endgenerate'''
    text=change(text,old,new)
    old='''    rv32_frequency_line_extract32 response_extract (
        .line_i(dcache_resp_line_data_i),.offset_i(response_query_offset),
        .size_i(2'd2),.unsigned_i(1'b1),.value_o(response_line_word));'''
    new='''    generate if(RESPONSE_QUERY_PREDECODE!=0) begin:g_direct_response_extract
        wire [16*32-1:0] windows;
        for(genvar byte_offset=0;byte_offset<16;byte_offset=byte_offset+1) begin:g_byte
            for(genvar window_bit=0;window_bit<32;window_bit=window_bit+1) begin:g_bit
                localparam integer LINE_BIT=byte_offset*8+window_bit;
                if(LINE_BIT<128) begin:g_present
                    assign windows[byte_offset*32+window_bit]=dcache_resp_line_data_i[LINE_BIT];
                end else begin:g_zero
                    assign windows[byte_offset*32+window_bit]=1'b0;
                end
            end
        end
        rv32_frequency_event_select #(.WIDTH(32),.EVENTS(16),.PRIORITY(0)) response_extract (
            .events_i(response_query_offset),.values_i(windows),.write_o(),.value_o(response_line_word));
    end else begin:g_original_response_extract
        rv32_frequency_line_extract32 response_extract (
            .line_i(dcache_resp_line_data_i),.offset_i(response_query_offset),
            .size_i(2'd2),.unsigned_i(1'b1),.value_o(response_line_word));
    end endgenerate'''
    return change(text,old,new)


def backend(text):
    text=change(text,'    parameter integer LSQ_ROB_QUERY_PREDECODE = 0',
        '    parameter integer LSQ_ROB_QUERY_PREDECODE = 0,\n    parameter integer LSQ_RESPONSE_QUERY_PREDECODE = 0')
    return change(text,'.REPORT_ROB_PREDECODE(LSQ_ROB_QUERY_PREDECODE), .TAG_WIDTH(TAG_WIDTH),',
        '.REPORT_ROB_PREDECODE(LSQ_ROB_QUERY_PREDECODE), .RESPONSE_QUERY_PREDECODE(LSQ_RESPONSE_QUERY_PREDECODE), .TAG_WIDTH(TAG_WIDTH),')


def core(text):
    return change(text,'    rv32_backend_joint #(.STORE_ALLOC_EARLY_ADDRESS(2),',
        '    rv32_backend_joint #(.LSQ_RESPONSE_QUERY_PREDECODE(1), .STORE_ALLOC_EARLY_ADDRESS(2),')


def main():
    parent=ROOT/'EI_eg_registered_shared_store_probe'
    verify_parent(parent)
    out=prepare('EJ_lsq_response_query_predecode',parent,
        {'rtl/backend/rv32_lsq.v':lsq,'rtl/backend/rv32_backend_joint.v':backend,'rtl/cpu_core.v':core},
        'Conditional EI child for measured EF response paths: select original full response-match row payload directly with highest-row priority and exact row-zero default. Query a saved-offset one-hot code, then select fixed zero-padded 32-bit byte windows; preserve original forwarding merge, formatting and response updates. Source-only, unadopted/unmeasured, no new state or cycles.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['lsq_direct_response_query_and_predecoded_byte_routing'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EF_20261005',
        behavior='Original response_match/slot/fire, full tag+generation+response_wait authority, line-valid mux, forwarding merge, LB/LH/LW formatting, recovery and clocked updates preserved. Default disabled mode retains binary query/extractor.',
        timing_tradeoff='Avoids response-match row encode then query-row decode and late binary offset driving four barrel stages. Adds 12 combinational query bits per row, one-hot fixed-window routing and selector loads; new area/frequency unknown.',
        current_response_query_packet_width=72,additional_response_query_combinational_bits_per_row=12,
        existing_clocked_payload_refactor='No changed clocked source; no new FF/latency/handshake.',
        limiting_path_evidence='F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json',
        adoption_condition='Complete source review and examine remaining mapped response-control loads; report final combined scope before any next measurement.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
