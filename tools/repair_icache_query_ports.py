"""Repair two child port bindings; no architecture change and no EDA."""
from prepare_staged_frequency_candidate import change,prepare,ROOT

def ports(t):
    t=change(t,'.lookup_req_pc(lookup_req_pc)', '.if_req_pc_i(lookup_req_pc)')
    return change(t,'.lookup_req_epoch(lookup_req_epoch)', '.if_req_epoch_i(lookup_req_epoch)')

if __name__=='__main__':
    prepare('L1_repaired_icache_ports',ROOT/'L_local_recovery_queries',
            {'rtl/cache/rv32_icache_nonblocking.v':ports},
            'L with two Icache MSHR row named-port bindings restored; parent signals and architecture unchanged')
