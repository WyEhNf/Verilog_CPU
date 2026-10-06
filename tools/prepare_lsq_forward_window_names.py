"""Correct a reserved identifier during source review; no HDL tools."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def names(t):
    t=change(t,'            wire [3:0] matches;','            wire [3:0] byte_match_bits;')
    t=change(t,'                assign matches[store_byte]=match_view;',
               '                assign byte_match_bits[store_byte]=match_view;')
    return change(t,'            assign mask_o[load_byte]=|matches;',
                  '            assign mask_o[load_byte]=|byte_match_bits;')


if __name__=='__main__':
    prepare('DF1_lsq_forward_windows_names',ROOT/'DF_lsq_forward_windows',
            {'rtl/backend/rv32_lsq.v':names},
            'DF source-review correction: byte_match_bits replaces the SystemVerilog '
            'reserved identifier matches; architecture and behavior unchanged')
