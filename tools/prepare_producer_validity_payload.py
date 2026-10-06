"""Remove valid-controlled zero muxes from producer payloads, no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


def unmask(t):
    start=t.index('        for (producer_index = 0; producer_index < BE_WIDTH;')
    stop=t.index('        if (mdu_completion_valid) begin',start)
    alu=t[start:stop]
    payload_pattern=re.compile(r'^                producer_(?:tag|phys|value|addr|branch_target|store_data)_r\[[^\n]* = [^\n]*;\n',re.M)
    payload=payload_pattern.findall(alu)
    if len(payload)!=6: raise ValueError('Expected six ALU payload assignments')
    alu=payload_pattern.sub('',alu)
    anchor='        for (producer_index = 0; producer_index < BE_WIDTH; producer_index = producer_index + 1) begin\n'
    alu=change(alu,anchor,anchor+''.join(line[4:] for line in payload)+
        '            // Payload follows its retained source independently of valid.\n')
    t=t[:start]+alu+t[stop:]
    t=change(t,'''        if (mdu_completion_valid) begin
            producer_valid_r[MDU_SOURCE] = 1'b1; producer_target_live_r[MDU_SOURCE] = 1'b1; producer_tag_r[MDU_SOURCE*TAG_WIDTH +: TAG_WIDTH] = mdu_completion_tag; producer_phys_r[MDU_SOURCE*PAW +: PAW] = mdu_completion_phys; producer_value_r[MDU_SOURCE*32 +: 32] = mdu_completion_value; producer_rd_we_r[MDU_SOURCE] = mdu_completion_rd_we;
        end
        if (lsq_load_complete_valid) begin
            producer_valid_r[LSQ_SOURCE] = 1'b1; producer_target_live_r[LSQ_SOURCE] = 1'b1; producer_tag_r[LSQ_SOURCE*TAG_WIDTH +: TAG_WIDTH] = lsq_load_complete_tag; producer_phys_r[LSQ_SOURCE*PAW +: PAW] = lsq_phys_mem[lsq_load_complete_lsq_tag[3 +: LSQ_SLOT_WIDTH]]; producer_value_r[LSQ_SOURCE*32 +: 32] = lsq_load_complete_value; producer_rd_we_r[LSQ_SOURCE] = 1'b1; producer_load_r[LSQ_SOURCE] = 1'b1; producer_memory_r[LSQ_SOURCE] = 1'b1;
        end''',
        '''        producer_tag_r[MDU_SOURCE*TAG_WIDTH +: TAG_WIDTH]=mdu_completion_tag;
        producer_phys_r[MDU_SOURCE*PAW +: PAW]=mdu_completion_phys;
        producer_value_r[MDU_SOURCE*32 +: 32]=mdu_completion_value;
        producer_tag_r[LSQ_SOURCE*TAG_WIDTH +: TAG_WIDTH]=lsq_load_complete_tag;
        producer_phys_r[LSQ_SOURCE*PAW +: PAW]=lsq_phys_mem[lsq_load_complete_lsq_tag[3 +: LSQ_SLOT_WIDTH]];
        producer_value_r[LSQ_SOURCE*32 +: 32]=lsq_load_complete_value;
        if (mdu_completion_valid) begin
            producer_valid_r[MDU_SOURCE]=1'b1;
            producer_target_live_r[MDU_SOURCE]=1'b1;
            producer_rd_we_r[MDU_SOURCE]=mdu_completion_rd_we;
        end
        if (lsq_load_complete_valid) begin
            producer_valid_r[LSQ_SOURCE]=1'b1;
            producer_target_live_r[LSQ_SOURCE]=1'b1;
            producer_rd_we_r[LSQ_SOURCE]=1'b1;
            producer_load_r[LSQ_SOURCE]=1'b1;
            producer_memory_r[LSQ_SOURCE]=1'b1;
        end''')
    return t


if __name__=='__main__':
    prepare('AR_producer_validity_owned_payload',ROOT/'AQ_icache_mshr_validity_owned_payload',
            {'rtl/backend/rv32_backend_joint.v':unmask},
            'AQ plus unconditional retained producer tag/phys/value/address/target/store-data buses with unchanged producer-valid/target-live/metadata arbitration; completion and RS consumers qualify by valid before use; removes wide zero gating under ALU/MDU/LSQ valid without latency/FF change; no EDA')
