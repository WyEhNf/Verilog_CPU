"""Repair an internal SystemVerilog reserved identifier, no logic changes."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare


def rename_reserved(expected):
    def transform(t):
        if re.search(r'\brow_match_mask\b',t):
            raise ValueError('Preserve existing identifier: row_match_mask')
        t,count=re.subn(r'\bmatches\b','row_match_mask',t)
        if count!=expected: raise ValueError('Reserved identifier inventory '+str(count))
        return t
    return transform


if __name__=='__main__':
    prepare('CD1_sv_identifier_repair',ROOT/'CD_predictor_outer_and_ras_routing',{
        'rtl/backend/rv32_backend_joint.v':rename_reserved(6),
        'rtl/backend/rv32_rat_recovery.v':rename_reserved(6),
        'rtl/backend/rv32_rob.v':rename_reserved(6),
        'rtl/backend/rv32_store_address_select.v':rename_reserved(3),
        'rtl/rv32_rename_unit.v':rename_reserved(6),
    },'CD with only 27 whole-token internal matches identifiers renamed row_match_mask in five files; Verilator 5.020 treats matches as a SystemVerilog keyword. No ports, state, parameters, equations, clock edges or architecture changed. Retain CD failed build and stopped synth logs; no extra optimization or standalone test')
