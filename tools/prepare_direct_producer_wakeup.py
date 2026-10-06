"""Bypass completion arbitration in direct-mode physical-register wakeup."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


def backend(t):
    t=change(t,'    localparam integer RS_WAKE_WIDTH = BE_WIDTH + PRODUCERS;',
             '''    // In direct completion modes every CDB packet is a view of a
    // still-valid held producer. That producer already broadcasts to RS.
    localparam integer RS_DIRECT_WAKE=(RS_PHYSICAL_WAKEUP!=0) &&
        ((COMPLETION_BYPASS==1) || (COMPLETION_BYPASS==2));
    localparam integer RS_WAKE_WIDTH = RS_DIRECT_WAKE ? PRODUCERS : BE_WIDTH+PRODUCERS;''')
    t=change(t,'.SOURCE_TAG_WIDTH(RS_SOURCE_TAG_WIDTH), .WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL)',
             '.SOURCE_TAG_WIDTH(RS_SOURCE_TAG_WIDTH), .WAKE_UNIQUE_OWNER(RS_DIRECT_WAKE), .WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL)')
    t=change(t,'''    assign rs_wake_valid = {
        producer_valid & producer_rd_we & producer_target_live_r,
        wake_wb_valid
    };''','''    generate if(RS_DIRECT_WAKE!=0) begin:g_direct_producer_wake
        assign rs_wake_valid=producer_valid & producer_rd_we & producer_target_live_r;
        assign rs_wake_value=producer_value;
    end else begin:g_queued_or_legacy_wake
        assign rs_wake_valid={producer_valid & producer_rd_we & producer_target_live_r,wake_wb_valid};
        assign rs_wake_value={producer_value,wake_wb_value};
    end endgenerate''')
    t=change(t,'            if(wake_identity_lane<BE_WIDTH) begin:g_completed',
             '''            if(RS_DIRECT_WAKE!=0) begin:g_direct_producer
                assign phys=producer_phys[wake_identity_lane*PAW +: PAW];
            end else if(wake_identity_lane<BE_WIDTH) begin:g_completed''')
    return change(t,'    assign rs_wake_value = {producer_value, wake_wb_value};\n','')


def station(t):
    t=change(t,'    parameter integer SOURCE_TAG_WIDTH = TAG_WIDTH,',
             '''    parameter integer SOURCE_TAG_WIDTH = TAG_WIDTH,
    // Only select this for a bus containing one live producer per physical
    // destination; generic callers retain first/last duplicate-tag priority.
    parameter integer WAKE_UNIQUE_OWNER = 0,''')
    start=t.index('                if (wl == 0) begin : g_first')
    end=t.index('\n            end\n            rv32_frequency_event_select',start)
    original=t[start:end]
    replacement='''                if(WAKE_UNIQUE_OWNER!=0) begin:g_unique_owner
                    assign first1[wl]=wake1_match[wr][wl];
                    assign last1[wl]=wake1_match[wr][wl];
                    assign first2[wl]=wake2_match[wr][wl];
                    assign last2[wl]=wake2_match[wr][wl];
                end else begin:g_ordered_duplicates
'''+original+'''\n                end'''
    t=t[:start]+replacement+t[end:]
    # First selectors are always used. Under unique ownership there is no
    # distinct clocked last-match value; share the already selected word.
    last1='''            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) last1_selector (
                .events_i(last1),.values_i(local_values),.write_o(),.value_o(wake1_last[wr]));'''
    last2='''            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) last2_selector (
                .events_i(last2),.values_i(local_values),.write_o(),.value_o(wake2_last[wr]));'''
    t=change(t,last1,'')
    t=change(t,last2,'''            if(WAKE_UNIQUE_OWNER!=0) begin:g_shared_wake_word
                assign wake1_last[wr]=wake1_first[wr];
                assign wake2_last[wr]=wake2_first[wr];
            end else begin:g_last_wake_word
'''+last1+'\n'+last2+'''\n            end''')
    return t


if __name__=='__main__':
    prepare('CA_direct_physical_producer_wakeup',ROOT/'BZ_bounded_rs_operand_writes',{
        'rtl/backend/rv32_backend_joint.v':backend,
        'rtl/backend/rv32_reservation_station.v':station,
    },'BZ plus direct completion physical wake bus uses only held live producers: current WAKE_WIDTH 10 to 6, remove CDB arbitration/tag/value feedback into RS; rename gives distinct live physical destinations, so wake match is one-hot and first/last data are shared without duplicate priority prefix; ROB generation/recovery filtering and consumer same-edge readiness unchanged, queued completion and legacy caller defaults retain original buses and first/last semantics; no extra FF/cycles, area/IPC/Fmax unmeasured, no EDA')
