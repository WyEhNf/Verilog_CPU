"""Combine DY with two saved-netlist-driven locality changes; source only."""
import hashlib
import json
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def rat(t):
    t=change(t, '''        wire [ROB_ENTRIES-1:0] raw_killed,raw_upper,killed,upper;''',
             '''        localparam integer ARCH_DOMAINS=(31+3)/4;
        wire [ROB_ENTRIES-1:0] raw_killed,raw_upper;
        wire [ARCH_DOMAINS*ROB_ENTRIES-1:0] killed,upper;''')
    t=change(t, '''        rv32_frequency_control_tree #(.WIDTH(ROB_ENTRIES),.LEAVES(1)) killed_tree (''',
             '''        // One leaf serves at most four architectural registers.
        // Keep the exact old killed/upper predicates; isolate their consumers.
        rv32_frequency_control_tree #(.WIDTH(ROB_ENTRIES),.LEAVES(ARCH_DOMAINS)) killed_tree (''')
    t=change(t, '        rv32_frequency_control_tree #(.WIDTH(ROB_ENTRIES),.LEAVES(1)) upper_tree (',
             '        rv32_frequency_control_tree #(.WIDTH(ROB_ENTRIES),.LEAVES(ARCH_DOMAINS)) upper_tree (')
    t=change(t, '''                assign row_match_mask[row]=killed[row] && rd_i[row*5 +: 5]==arch;
                assign upper_matches[row]=row_match_mask[row] && upper[row];''',
             '''                localparam integer ARCH_DOMAIN=(arch-1)/4;
                assign row_match_mask[row]=killed[ARCH_DOMAIN*ROB_ENTRIES+row] && rd_i[row*5 +: 5]==arch;
                assign upper_matches[row]=row_match_mask[row] && upper[ARCH_DOMAIN*ROB_ENTRIES+row];''')
    return t


def icache(t):
    start=t.index('module rv32_icache_query_queue #(')
    before,part=t[:start],t[start:]
    part=change(part, '''    reg [32+EPOCH_WIDTH-1:0] payload [0:1];
    wire read_local;
    rv32_frequency_control_tree #(.LEAVES(1)) read_tree (
        .signal_i(read_slot),.views_o(read_local));
    assign {pc_o,epoch_o}=read_local?payload[1]:payload[0];''',
             '''    localparam integer PAYLOAD_WIDTH=32+EPOCH_WIDTH;
    localparam integer PAYLOAD_WORDS=(PAYLOAD_WIDTH+15)/16;
    wire [PAYLOAD_WIDTH-1:0] payload [0:1];
    wire [PAYLOAD_WORDS-1:0] read_views;
    wire [PAYLOAD_WIDTH-1:0] read_payload;
    rv32_frequency_control_tree #(.LEAVES(PAYLOAD_WORDS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    assign {pc_o,epoch_o}=read_payload;
    genvar read_word;
    generate for(read_word=0;read_word<PAYLOAD_WORDS;read_word=read_word+1) begin:g_read_word
        localparam integer LOW=read_word*16;
        localparam integer BITS=(PAYLOAD_WIDTH-LOW>=16)?16:PAYLOAD_WIDTH-LOW;
        assign read_payload[LOW +: BITS]=read_views[read_word]?
            payload[1][LOW +: BITS]:payload[0][LOW +: BITS];
    end endgenerate''')
    part=change(part, '''        wire write_local;
        rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
            .signal_i(push && write_slot==queue_row),.views_o(write_local));
        always @(posedge clk_i) if(write_local) payload[queue_row]<={pc_i,epoch_i};''',
             '''        // Preserve the same two unreset payload slots and write edge.
        // Each write leaf now owns at most sixteen existing hold muxes.
        rv32_frequency_word_bank #(.WIDTH(PAYLOAD_WIDTH)) owner (
            .clk_i(clk_i),.write_i(push && write_slot==queue_row),
            .data_i({pc_i,epoch_i}),.data_o(payload[queue_row]));''')
    return before+part


def main():
    parent=ROOT/'DY_dm1_locality_and_store_simm12'
    verify_parent(parent)
    out=prepare('DZ_recovery_and_icache_queue_domains',parent,
        {'rtl/backend/rv32_rat_recovery.v':rat,'rtl/cache/rv32_icache_nonblocking.v':icache},
        'Combine DY with eight architectural RAT recovery predicate domains and bounded I-cache request payload read/write ownership. Saved DM1/DT mapped input-load evidence shows RAT upper predicates around 80-90 pins and I-cache request write leaves at 72 pins. Preserve exact recovery masks, two queue payload slots and all handshake/count/epoch state; no EDA or program run.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','shared_store_signed_12bit_adder',
        'negative_polarity_distribution','local_lsq_request_and_forwarding_owner',
        'lsq_report_rob_slot_predecode','rat_recovery_architectural_domains',
        'icache_request_queue_word_owners'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,mapped_gain_proven=False,
        rat_recovery_architectural_domains=8,max_architectural_registers_per_recovery_leaf=4,
        icache_request_queue_existing_payload_slot_count=2,
        icache_request_queue_payload_bits_per_read_write_leaf=16,
        queue_clocked_source_refactor='Same payload state is moved to the existing word-bank owner. Count, read-slot, write-slot, epoch comparison and push/pop timing are unchanged. Source text of payload clock blocks therefore differs, requiring manual state correspondence rather than whole-file clock-block-text equality.')
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
                          tests_started=False,adopted=False)))


if __name__=='__main__':main()
