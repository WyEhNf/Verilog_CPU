"""Prepare an optional grouped RAT recovery implementation, source only."""
from prepare_staged_frequency_candidate import change,prepare,ROOT


def grouped_recovery(t):
    t=change(t,'    genvar row, arch, bit_id;', '    genvar row, arch, bit_id, group;')
    t=change(t,'    end else begin : g_parallel_oldest', '    end else if(IMPL==1) begin : g_parallel_oldest')
    t=change(t,'    end endgenerate\n    generate for (arch = 0;', '''    end else begin:g_local_oldest
        localparam integer GROUPS=(ROB_ENTRIES+7)/8;
        // Power-of-two ROB geometry makes narrow subtraction exactly the
        // wrapped age. No per-row compare/mux or unsized 32-bit wrap adder.
        wire [SLOT_WIDTH-1:0] branch_age=branch_slot_i-head_i;
        wire [ROB_ENTRIES-1:0] raw_killed,raw_upper,killed,upper;
        for(row=0;row<ROB_ENTRIES;row=row+1) begin:g_age
            wire [SLOT_WIDTH-1:0] row_age=row-head_i;
            assign raw_killed[row]=valid_i[row] && rd_we_i[row] &&
                row_age>branch_age && row_age<occupancy_i;
            assign raw_upper[row]=(row>branch_slot_i);
        end
        rv32_frequency_control_tree #(.WIDTH(ROB_ENTRIES),.LEAVES(1)) killed_tree (
            .signal_i(raw_killed),.views_o(killed));
        rv32_frequency_control_tree #(.WIDTH(ROB_ENTRIES),.LEAVES(1)) upper_tree (
            .signal_i(raw_upper),.views_o(upper));
        assign undo_result[0 +: PAW]=rat_i[0 +: PAW];
        for(arch=1;arch<32;arch=arch+1) begin:g_arch
            wire [ROB_ENTRIES-1:0] matches,upper_matches,first_any,first_upper;
            wire [GROUPS-1:0] any_group,upper_group;
            wire found=|any_group;
            wire upper_found=|upper_group;
            wire [PAW-1:0] any_value,upper_value;
            for(group=0;group<GROUPS;group=group+1) begin:g_group
                localparam integer LAST=((group+1)*8>ROB_ENTRIES)?ROB_ENTRIES-1:(group+1)*8-1;
                assign any_group[group]=|matches[LAST:group*8];
                assign upper_group[group]=|upper_matches[LAST:group*8];
            end
            for(row=0;row<ROB_ENTRIES;row=row+1) begin:g_match
                localparam integer GROUP=row/8;
                localparam integer FIRST=GROUP*8;
                wire any_before_group,upper_before_group,any_before_row,upper_before_row;
                assign matches[row]=killed[row] && rd_i[row*5 +: 5]==arch;
                assign upper_matches[row]=matches[row] && upper[row];
                if(GROUP==0) begin:g_first_group
                    assign any_before_group=0;assign upper_before_group=0;
                end else begin:g_later_group
                    assign any_before_group=|any_group[GROUP-1:0];
                    assign upper_before_group=|upper_group[GROUP-1:0];
                end
                if(row==FIRST) begin:g_first_row
                    assign any_before_row=0;assign upper_before_row=0;
                end else begin:g_later_row
                    assign any_before_row=|matches[row-1:FIRST];
                    assign upper_before_row=|upper_matches[row-1:FIRST];
                end
                assign first_any[row]=matches[row] && !any_before_row && !any_before_group;
                assign first_upper[row]=upper_matches[row] && !upper_before_row && !upper_before_group;
            end
            for(bit_id=0;bit_id<PAW;bit_id=bit_id+1) begin:g_payload
                wire [ROB_ENTRIES-1:0] any_column,upper_column;
                for(row=0;row<ROB_ENTRIES;row=row+1) begin:g_row
                    assign any_column[row]=first_any[row] && old_phys_i[row*PAW+bit_id];
                    assign upper_column[row]=first_upper[row] && old_phys_i[row*PAW+bit_id];
                end
                assign any_value[bit_id]=|any_column;
                assign upper_value[bit_id]=|upper_column;
            end
            // Select between two completed values, rather than broadcasting
            // upper_found into 64 priority inputs per architectural register.
            assign undo_result[arch*PAW +: PAW]=found?
                (upper_found?upper_value:any_value):rat_i[arch*PAW +: PAW];
        end
    end endgenerate
    generate for (arch = 0;''')
    t=change(t,'(IMPL != 0 && IMPL != 1)', '(IMPL < 0 || IMPL > 2)')
    return t


def enable_grouped(t):
    return change(t,'.PAW(PAW), .IMPL(1)) rat_recovery (', '.PAW(PAW), .IMPL(2)) rat_recovery (')


if __name__=='__main__':
    prepare('N_grouped_rat_recovery',ROOT/'M_registered_free_pool',
            {'rtl/backend/rv32_rat_recovery.v':grouped_recovery,'rtl/backend/rv32_backend_joint.v':enable_grouped},
            'Separate untested alternative: M plus exact narrow modular age, independent first-any/first-upper grouped selection, late value choice and priced killed/upper query domains; no new recovery cycle')
