"""Regenerate two intended field-owner modules from preserved RTL, no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare
from prepare_lsq_owned_fields import owned_lsq
from prepare_rob_owned_fields import owned_rob, narrow_lsq
from prepare_owner_optimization_visibility import expose


def repaired_lsq(_):
    original = (ROOT / 'T_bounded_payload_consumers/rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    return expose('rv32_lsq_owned_field')(narrow_lsq(owned_lsq(original)))


def repaired_rob(_):
    original = (ROOT / 'V_local_producer_tag_table/rtl/backend/rv32_rob.v').read_text(encoding='utf-8')
    return expose('rv32_rob_owned_field')(owned_rob(original))


if __name__ == '__main__':
    prepare('AE_correct_statement_ownership', ROOT / 'AD_reserved_dispatch_boundary',
            {'rtl/backend/rv32_rob.v': repaired_rob, 'rtl/backend/rv32_lsq.v': repaired_lsq},
            'AD with ROB/LSQ field ownership regenerated from original sources using statement-aware NBA extraction; preserve <= age comparisons and single-line if guards; no EDA run')
