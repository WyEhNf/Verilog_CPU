"""Repair a manually found recovery source name; no HDL/EDA invocation."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def backend(source):
    return change(source,
        '.signal_i({recovery_apply,recovery_descriptor_occupancy,recovery_descriptor_head,execution_branch_age}),',
        '.signal_i({recovery_domains[6],recovery_descriptor_occupancy,recovery_descriptor_head,execution_branch_age}),')


if __name__=='__main__':
    prepare('CX1_execution_local_cancel_source_fix',ROOT/'CX_execution_local_cancel',
            {'rtl/backend/rv32_backend_joint.v':backend},
            'Manual source repair: backend apply signal is recovery_domains[6], not undeclared recovery_apply; preserved failed source candidate; no HDL/EDA tests')
