"""Localize ROB banked commit payload selection on the untested EE batch."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def rob(text):
    start=text.index('                wire [BANK_ROWS-1:0] row_select;')
    end=text.index('\n            end\n        end\n    endgenerate',start)
    old=text[start:end]
    assert old.count('assign bank_packet[commit_bank] = packet;')==1
    new='''                wire [BANK_ROWS-1:0] row_select;
                wire [BANK_ROWS*COMMIT_READ_WIDTH-1:0] row_packets;
                for (bank_row = 0; bank_row < BANK_ROWS; bank_row = bank_row + 1) begin : g_row
                    wire [BE_WIDTH-1:0] possible_heads;
                    // Preserve the original four-consecutive-heads query,
                    // including the exact modulo indexing for every bank.
                    for (bank_offset = 0; bank_offset < BE_WIDTH; bank_offset = bank_offset + 1) begin : g_head
                        assign possible_heads[bank_offset] = head_row_select[
                            (bank_row*BE_WIDTH+commit_bank+ROB_ENTRIES-bank_offset)%ROB_ENTRIES];
                    end
                    assign row_select[bank_row] = |possible_heads;
                    assign row_packets[bank_row*COMMIT_READ_WIDTH +: COMMIT_READ_WIDTH]={
                        valid_mem[bank_row*BE_WIDTH+commit_bank], ready_mem[bank_row*BE_WIDTH+commit_bank],
                        store_mem[bank_row*BE_WIDTH+commit_bank], halt_mem[bank_row*BE_WIDTH+commit_bank],
                        error_mem[bank_row*BE_WIDTH+commit_bank], store_wait_mem[bank_row*BE_WIDTH+commit_bank],
                        store_sent_mem[bank_row*BE_WIDTH+commit_bank], generation_mem[bank_row*BE_WIDTH+commit_bank],
                        rd_we_mem[bank_row*BE_WIDTH+commit_bank], rd_mem[bank_row*BE_WIDTH+commit_bank],
                        pc_mem[bank_row*BE_WIDTH+commit_bank], inst_mem[bank_row*BE_WIDTH+commit_bank],
                        value_mem[bank_row*BE_WIDTH+commit_bank], store_addr_mem[bank_row*BE_WIDTH+commit_bank],
                        store_mask_mem[bank_row*BE_WIDTH+commit_bank], store_data_mem[bank_row*BE_WIDTH+commit_bank],
                        old_phys_mem[bank_row*BE_WIDTH+commit_bank], new_phys_mem[bank_row*BE_WIDTH+commit_bank]};
                end
                // PRIORITY=0 is the same bitwise OR of masked row packets
                // as the old loop, even for multiple asserted row_select bits.
                // Its existing control trees bound each final data group.
                rv32_frequency_event_select #(.WIDTH(COMMIT_READ_WIDTH),.EVENTS(BANK_ROWS),.PRIORITY(0)) packet_selector (
                    .events_i(row_select),.values_i(row_packets),.write_o(),
                    .value_o(bank_packet[commit_bank]));'''
    return text[:start]+new+text[end:]


def main():
    parent=ROOT/'EE_lsq_direct_report_and_forward_hold'
    verify_parent(parent)
    out=prepare('EF_rob_commit_packet_domains',parent,
        {'rtl/backend/rv32_rob.v':rob},
        'EE plus grouped banked ROB commit read: same row-select query, same field order and bank rotation, masked packet OR through existing <=16-bit selection domains. No new FF, cycles or commit permissions. Inherits the only behavioral tradeoff, disabled allocation-edge early store address. Source-only complete combination, unmeasured.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['rob_banked_commit_payload_selection_domains'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        existing_clocked_payload_refactor='Inherited EE forwarding hold: same 36 unreset bits/data/write edge; no ROB state moves.',
        behavior='Inherits ED allocation-address availability tradeoff; direct LSQ report, saved forwarding domains and ROB commit packet OR otherwise preserve logic/handshake/cycles. Ordinary integer pipeline remains 10 stages.',
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EA_20261005',
        source_algebra='ROB bank packet = bitwise OR of each row_select replicated over the identical row packet. PRIORITY=0 event selector computes that same expression with balanced OR and bounded leaf controls; no one-hot invariant needed.',
        adoption_condition='Review full EA-to-EF source scope, preserve EA result, freeze and report before one timing-only measurement. Do not measure ED, EE or ROB-only intermediates.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
