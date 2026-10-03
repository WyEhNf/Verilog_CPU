"""Keep electrical inversion boundaries but expose state to pruning; no EDA."""
from prepare_staged_frequency_candidate import change, prepare, ROOT


def expose(module):
    def transform(t):
        return change(t,'(* keep_hierarchy = 1 *)\nmodule '+module,
                      '// State logic may flatten and prune unused bits. Kept inversion\n'
                      '// modules inside the write trees retain the electrical domains.\nmodule '+module)
    return transform


if __name__=='__main__':
    prepare('AC_visible_state_optimization', ROOT/'AB_registered_final_multiplier_cpa',
            {'rtl/backend/rv32_rob.v':expose('rv32_rob_owned_field'),
             'rtl/backend/rv32_lsq.v':expose('rv32_lsq_owned_field'),
             'rtl/cpu_core.v':expose('rv32_decode_field_bank'),
             'rtl/frontend/rv32_fetch_frontend.v':expose('rv32_frontend_queue_payload_bank')},
            'AB plus flattenable state owners so unused/debug payload and constant bits remain visible to course pruning; preserve every complete inversion module and kept leaf instance, no register/cycle change, no EDA run')
