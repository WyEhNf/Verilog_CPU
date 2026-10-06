"""Exclude invalid ALU payload from redirect-ready arbitration, no EDA."""
from prepare_staged_frequency_candidate import ROOT,prepare,change


def qualify(t):
    return change(t,'''            if (alu_exec_is_load[alu_ready_lane]) begin
                alu_exec_ready_r[alu_ready_lane] = 1'b1;''',
                 '''            // Payload may retain a former result after its valid bit
            // clears. An empty slot cannot reserve the single redirect grant.
            if (!alu_exec_valid[alu_ready_lane]) begin
                alu_exec_ready_r[alu_ready_lane] = 1'b1;
            end else if (alu_exec_is_load[alu_ready_lane]) begin
                alu_exec_ready_r[alu_ready_lane] = 1'b1;''')


if __name__=='__main__':
    prepare('AM_valid_alu_redirect_ownership',ROOT/'AL_alu_validity_owned_payload',
            {'rtl/backend/rv32_backend_joint.v':qualify},
            'AL plus valid-qualified ALU ready/redirect arbitration: empty slots advertise ready without claiming branch capture grant; prevents stale invalid branch flags from blocking a real redirect, consistent with validity-owned payload; no EDA run')
