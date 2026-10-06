"""Prepare byte-local refill merge qualifications; source only, no EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def byte_merge(t):
    return change(t, '''        wire [7:0] refill_data=(response_store_i && response_mask_i[byte_id])?
            response_store_data_i[byte_id*8 +: 8]:response_data_i[byte_id*8 +: 8];''',
        '''        // Qualify before a preserved boundary. The raw store-response
        // command reaches sixteen byte qualifications, not 128 data mux bits.
        // Each final byte selection controls only eight payload mux bits.
        wire merge_store_byte;
        rv32_frequency_control_tree #(.LEAVES(1)) merge_selection_tree (
            .signal_i(response_store_i && response_mask_i[byte_id]),
            .views_o(merge_store_byte));
        wire [7:0] refill_data=merge_store_byte?
            response_store_data_i[byte_id*8 +: 8]:response_data_i[byte_id*8 +: 8];''')


if __name__ == '__main__':
    prepare('DH_dcache_merge_controls', ROOT/'DF1_lsq_forward_windows_names',
        {'rtl/cache/rv32_dcache_nonblocking.v': byte_merge},
        'Preserve byte-qualified refill merge controls before eight data mux bits; no new state, macros, ports, or cycles.')
