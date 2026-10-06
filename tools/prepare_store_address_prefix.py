"""Prepare a prefix/carry-select shared store AGU; no HDL or measurement tools."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


ADD32 = '''

// Eight independent four-bit adders produce block G/P and both sum choices.
// Three prefix levels resolve carries. Each late carry selects four bits.
// Exact modulo-2^32 addition with no registers or additional clock edge.
(* keep_hierarchy = 1 *)
module rv32_frequency_add32_select (
    input wire [31:0] lhs_i,rhs_i,
    output wire [31:0] sum_o
);
    wire [7:0] generate_stage [0:3];
    wire [7:0] propagate_stage [0:3];
    wire [3:0] sum_zero [0:7],sum_one [0:7];
    genvar block_index,prefix_level;
    generate
        for(block_index=0;block_index<8;block_index=block_index+1) begin:g_block
            wire [4:0] block_sum={1'b0,lhs_i[block_index*4 +: 4]}+
                {1'b0,rhs_i[block_index*4 +: 4]};
            assign sum_zero[block_index]=block_sum[3:0];
            assign sum_one[block_index]=block_sum[3:0]+4'd1;
            assign generate_stage[0][block_index]=block_sum[4];
            assign propagate_stage[0][block_index]=
                &(lhs_i[block_index*4 +: 4] ^ rhs_i[block_index*4 +: 4]);
            if(block_index==0) begin:g_first
                assign sum_o[0 +: 4]=sum_zero[0];
            end else begin:g_selected
                assign sum_o[block_index*4 +: 4]=generate_stage[3][block_index-1] ?
                    sum_one[block_index] : sum_zero[block_index];
            end
        end
        for(prefix_level=0;prefix_level<3;prefix_level=prefix_level+1) begin:g_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(block_index=0;block_index<8;block_index=block_index+1) begin:g_block
                if(block_index>=DISTANCE) begin:g_combine
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index] |
                        (propagate_stage[prefix_level][block_index] && generate_stage[prefix_level][block_index-DISTANCE]);
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index] &&
                        propagate_stage[prefix_level][block_index-DISTANCE];
                end else begin:g_copy
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index];
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index];
                end
            end
        end
    endgenerate
endmodule
'''


def shared_agu(t):
    return change(t, '        assign shared_store_addr = selected_base + selected_imm;',
        '''        rv32_frequency_add32_select address_adder (
            .lhs_i(selected_base),.rhs_i(selected_imm),.sum_o(shared_store_addr));''')


if __name__ == '__main__':
    prepare('DK_store_address_prefix', ROOT/'DJ_store_address_onehot',
        {'rtl/backend/rv32_backend_joint.v': shared_agu,
         'rtl/common/rv32_asap7_fanout.v': lambda t: t+ADD32},
        'Replace the shared store AGU long carry chain with eight parallel four-bit sum choices and a three-level carry prefix; combine DH/DI/DJ with no state, capacity, or cycle changes.')
