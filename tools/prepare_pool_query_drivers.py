"""Prepare local free-pool bitmap queries; source-only follow-up to N."""
from prepare_staged_frequency_candidate import change,prepare,ROOT

def pool_query_domains(t):
    t=change(t,'    genvar pool_index,pool_phys;', '''    wire [BE_WIDTH*PHYS_ADDR_WIDTH-1:0] pool_ids,pool_ids_local;
    wire [BE_WIDTH-1:0] pool_valid,pool_valid_local;
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(1)) pool_id_tree (
        .signal_i(pool_ids),.views_o(pool_ids_local));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(1)) pool_valid_tree (
        .signal_i(pool_valid),.views_o(pool_valid_local));
    genvar pool_index,pool_phys;''')
    t=change(t,'    generate for(pool_index=0;pool_index<BE_WIDTH;pool_index=pool_index+1) begin:g_pool_slot', '''    generate for(pool_index=0;pool_index<BE_WIDTH;pool_index=pool_index+1) begin:g_pool_slot
        assign pool_ids[pool_index*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]=pool_candidate[pool_index];
        assign pool_valid[pool_index]=pool_index<pool_count;''')
    t=change(t,'assign matches[pool_index]=(pool_index<pool_count) && pool_candidate[pool_index]==pool_phys;',
             'assign matches[pool_index]=pool_valid_local[pool_index] && pool_ids_local[pool_index*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==pool_phys;')
    return t

if __name__=='__main__':
    prepare('O_local_free_pool_queries',ROOT/'N_grouped_rat_recovery',
            {'rtl/rv32_rename_unit.v':pool_query_domains},
            'Separate untested alternative: N plus priced drivers for pool identity and validity bitmap query fanout; unchanged pool/recovery protocol and cycles')
