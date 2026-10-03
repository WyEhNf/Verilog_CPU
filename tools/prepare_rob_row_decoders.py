"""Make ROB row controls and wide completion selection local, no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare


LOCAL = r'''
    // Broadcast small metadata and data through bounded domains. Every row
    // qualifies its own updates before the final payload selection drivers.
    localparam integer WRITE_DOMAINS=4;
    localparam integer LOCAL_COMPLETION_DATA_WIDTH=101;
    localparam integer LOCAL_COMPLETION_WIDTH=3+TAG_WIDTH+LOCAL_COMPLETION_DATA_WIDTH;
    localparam integer LOCAL_COMPLETION_LEAVES=1<<$clog2(BE_WIDTH);
    wire [BE_WIDTH*LOCAL_COMPLETION_WIDTH-1:0] local_completion_input;
    wire [WRITE_DOMAINS*BE_WIDTH*LOCAL_COMPLETION_WIDTH-1:0] local_completion_domains;
    wire [2*ROB_ENTRIES-1:0] local_modes;
    wire [WRITE_DOMAINS*3*SLOT_WIDTH-1:0] local_indexes;
    wire [WRITE_DOMAINS*(BE_WIDTH+1)-1:0] local_commits;
    wire [WRITE_DOMAINS*(TAG_WIDTH+2)-1:0] local_acks;
    genvar command_row,command_lane,command_node;
    generate
    if(ALLOC_BANKED_WRITE!=0 && ROB_ENTRIES>=BE_WIDTH) begin:g_local_row_commands
        for(command_lane=0;command_lane<BE_WIDTH;command_lane=command_lane+1) begin:g_input
            wire mmio=(completion_store_addr_i[command_lane*32 +: 32]==32'h80000000) &&
                (completion_store_mask_i[command_lane*4 +: 4]==4'hf);
            assign local_completion_input[command_lane*LOCAL_COMPLETION_WIDTH +: LOCAL_COMPLETION_WIDTH]={
                completion_valid_i[command_lane],completion_done_i[command_lane],
                completion_error_i[command_lane],completion_tag_i[command_lane*TAG_WIDTH +: TAG_WIDTH],
                completion_value_i[command_lane*32 +: 32],
                completion_store_addr_i[command_lane*32 +: 32],
                completion_store_data_i[command_lane*32 +: 32],
                completion_store_mask_i[command_lane*4 +: 4],mmio};
        end
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*LOCAL_COMPLETION_WIDTH),.LEAVES(WRITE_DOMAINS)) completion_tree (
            .signal_i(local_completion_input),.views_o(local_completion_domains));
        rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(ROB_ENTRIES)) mode_tree (
            .signal_i({recovery_domains[5],reset_i}),.views_o(local_modes));
        rv32_frequency_control_tree #(.WIDTH(3*SLOT_WIDTH),.LEAVES(WRITE_DOMAINS)) index_tree (
            .signal_i({apply_age,head_commit_index,head_update_index}),.views_o(local_indexes));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH+1),.LEAVES(WRITE_DOMAINS)) commit_tree (
            .signal_i({commit_ready_i,commit_valid_o}),.views_o(local_commits));
        rv32_frequency_control_tree #(.WIDTH(TAG_WIDTH+2),.LEAVES(WRITE_DOMAINS)) ack_tree (
            .signal_i({store_ack_valid_i,store_ack_error_i,store_ack_tag_i}),.views_o(local_acks));
        for(command_row=0;command_row<ROB_ENTRIES;command_row=command_row+1) begin:g_row
            localparam integer DOMAIN=(command_row*WRITE_DOMAINS)/ROB_ENTRIES;
            wire row_reset=local_modes[command_row*2];
            wire row_recovery=local_modes[command_row*2+1];
            wire normal=!row_reset && !row_recovery;
            wire [SLOT_WIDTH-1:0] row_head,row_commit_head,row_branch_age;
            assign {row_branch_age,row_commit_head,row_head}=
                local_indexes[DOMAIN*3*SLOT_WIDTH +: 3*SLOT_WIDTH];
            wire [SLOT_WIDTH-1:0] row_age=command_row-row_head;
            wire killed=!row_reset && row_recovery &&
                (STAGED_RECOVERY ? recovery_saved_kill[command_row] :
                 (valid_mem[command_row] && row_age>row_branch_age && row_age<occupancy_reg));
            wire allocate=normal && bank_alloc_fire[command_row%BE_WIDTH] &&
                bank_alloc_slot[command_row%BE_WIDTH]==command_row;
            wire [BE_WIDTH-1:0] completion_match,completion_grant,completion_errors,retire_match;
            wire [LOCAL_COMPLETION_DATA_WIDTH-1:0] completion_mux [1:2*LOCAL_COMPLETION_LEAVES-1];
            for(command_lane=0;command_lane<LOCAL_COMPLETION_LEAVES;command_lane=command_lane+1) begin:g_complete
                if(command_lane<BE_WIDTH) begin:g_present
                    wire c_valid,c_done,c_error;
                    wire [TAG_WIDTH-1:0] c_tag;
                    wire [LOCAL_COMPLETION_DATA_WIDTH-1:0] c_data;
                    wire [3:0] c_select;
                    assign {c_valid,c_done,c_error,c_tag,c_data}=
                        local_completion_domains[(DOMAIN*BE_WIDTH+command_lane)*LOCAL_COMPLETION_WIDTH +: LOCAL_COMPLETION_WIDTH];
                    assign completion_match[command_lane]=!row_reset && c_valid && c_done &&
                        tag_matches(c_tag,command_row) && (!row_recovery || row_age<=row_branch_age);
                    if(command_lane==BE_WIDTH-1) begin:g_last
                        assign completion_grant[command_lane]=completion_match[command_lane];
                    end else begin:g_priority
                        assign completion_grant[command_lane]=completion_match[command_lane] &&
                            !(|completion_match[BE_WIDTH-1:command_lane+1]);
                    end
                    assign completion_errors[command_lane]=completion_match[command_lane] && c_error;
                    rv32_frequency_control_tree #(.LEAVES(4)) select_tree (
                        .signal_i(completion_grant[command_lane]),.views_o(c_select));
                    assign completion_mux[LOCAL_COMPLETION_LEAVES+command_lane]={
                        {32{c_select[3]}} & c_data[100:69],
                        {32{c_select[2]}} & c_data[68:37],
                        {32{c_select[1]}} & c_data[36:5],
                        {5{c_select[0]}} & c_data[4:0]};
                    wire [31:0] commit_offset=row_commit_head+command_lane;
                    wire [31:0] commit_slot=(commit_offset>=ROB_ENTRIES)?commit_offset-ROB_ENTRIES:commit_offset;
                    assign retire_match[command_lane]=normal &&
                        local_commits[DOMAIN*(BE_WIDTH+1)+BE_WIDTH] &&
                        local_commits[DOMAIN*(BE_WIDTH+1)+command_lane] && commit_slot==command_row;
                end else begin:g_padding
                    assign completion_mux[LOCAL_COMPLETION_LEAVES+command_lane]=0;
                end
            end
            for(command_node=1;command_node<LOCAL_COMPLETION_LEAVES;command_node=command_node+1) begin:g_or
                assign completion_mux[command_node]=completion_mux[2*command_node] | completion_mux[2*command_node+1];
            end
            wire completed=|completion_match;
            wire retire=|retire_match;
            wire ack_valid,ack_error;
            wire [TAG_WIDTH-1:0] ack_tag;
            assign {ack_valid,ack_error,ack_tag}=local_acks[DOMAIN*(TAG_WIDTH+2) +: TAG_WIDTH+2];
            wire acknowledged=normal && ack_valid && tag_matches(ack_tag,command_row);
            wire sent=normal && store_commit_valid_o && store_commit_ready_i && row_commit_head==command_row;
            wire [GENERATION_WIDTH-1:0] next_generation_local=
                (generation_next_mem[command_row]==0) ? {{(GENERATION_WIDTH-1){1'b0}},1'b1} : generation_next_mem[command_row];
            wire [GENERATION_WIDTH-1:0] generation_after_allocate=
                (next_generation_local=={GENERATION_WIDTH{1'b1}}) ?
                {{(GENERATION_WIDTH-1){1'b0}},1'b1} : next_generation_local+1'b1;
            wire allocation_error;
            wire [ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH-1:0] raw_allocation=
                bank_alloc_packet[command_row%BE_WIDTH][CHECKPOINT_WIDTH +: ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH];
            wire [31:0] completed_value,completed_addr,completed_data;
            wire [3:0] completed_mask;
            wire completed_mmio;
            assign {completed_value,completed_addr,completed_data,completed_mask,completed_mmio}=completion_mux[1];
            assign allocation_error=raw_allocation[ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH-4];
            always @* begin:g_commands
                // Wide D inputs have no global mode mux. Only local WE and
                // bounded select leaves consume the qualified update controls.
                {store_mem_write_data[command_row],branch_mem_write_data[command_row],
                 halt_mem_write_data[command_row],error_mem_write_data[command_row],
                 pc_mem_write_data[command_row],inst_mem_write_data[command_row],
                 rd_mem_write_data[command_row],rd_we_mem_write_data[command_row],
                 old_phys_mem_write_data[command_row],new_phys_mem_write_data[command_row]}=raw_allocation;
                store_mem_write_enable[command_row]=allocate;
                branch_mem_write_enable[command_row]=allocate;
                halt_mem_write_enable[command_row]=allocate;
                pc_mem_write_enable[command_row]=allocate;
                inst_mem_write_enable[command_row]=allocate;
                rd_mem_write_enable[command_row]=allocate;
                rd_we_mem_write_enable[command_row]=allocate;
                old_phys_mem_write_enable[command_row]=allocate;
                new_phys_mem_write_enable[command_row]=allocate;
                valid_mem_write_enable[command_row]=row_reset || killed || retire || allocate;
                valid_mem_write_data[command_row]=allocate;
                ready_mem_write_enable[command_row]=row_reset || killed || completed || retire || allocate;
                ready_mem_write_data[command_row]=!row_reset && !allocate && !retire && completed;
                store_wait_mem_write_enable[command_row]=row_reset || killed || acknowledged || retire || allocate;
                store_wait_mem_write_data[command_row]=!row_reset && !allocate && !retire && acknowledged;
                store_sent_mem_write_enable[command_row]=row_reset || killed || sent || retire || allocate;
                store_sent_mem_write_data[command_row]=!row_reset && !allocate && !retire && sent;
                error_mem_write_enable[command_row]=row_reset || allocate ||
                    (|completion_errors) || (acknowledged && ack_error);
                error_mem_write_data[command_row]=row_reset ? 1'b0 : (allocate ? allocation_error : 1'b1);
                generation_mem_write_enable[command_row]=row_reset || allocate;
                generation_mem_write_data[command_row]=row_reset ? {{(GENERATION_WIDTH-1){1'b0}},1'b1} : next_generation_local;
                generation_next_mem_write_enable[command_row]=row_reset || allocate;
                generation_next_mem_write_data[command_row]=row_reset ? {{(GENERATION_WIDTH-1){1'b0}},1'b1} : generation_after_allocate;
                value_mem_write_enable[command_row]=completed;
                value_mem_write_data[command_row]=completed_value;
                store_addr_mem_write_enable[command_row]=completed;
                store_addr_mem_write_data[command_row]=completed_addr;
                store_data_mem_write_enable[command_row]=completed;
                store_data_mem_write_data[command_row]=completed_data;
                store_mask_mem_write_enable[command_row]=completed;
                store_mask_mem_write_data[command_row]=completed_mask;
                mmio_word_mem_write_enable[command_row]=(MMIO_PREDECODE!=0) && completed;
                mmio_word_mem_write_data[command_row]=completed_mmio;
                checkpoint_mem_write_enable[command_row]=(CHECKPOINT_IMPL==0) && allocate;
                checkpoint_mem_write_data[command_row]=bank_alloc_packet[command_row%BE_WIDTH][0 +: CHECKPOINT_WIDTH];
            end
        end
    end else begin:g_legacy_field_commands
LEGACY
    end
    endgenerate
'''


def localize(t):
    start=t.index('    always @* begin : g_state_commands')
    stop=t.index('\n    always @(posedge clk_i) begin', start)
    original=t[start:stop]
    assert original.count('always @*')==1
    return t[:start]+LOCAL.replace('LEGACY',original)+t[stop:]


if __name__=='__main__':
    prepare('AF_row_local_rob_commands',ROOT/'AE_correct_statement_ownership',
            {'rtl/backend/rv32_rob.v':localize},
            'AE plus per-ROB-row mode/age/generation decode, bounded completion broadcast and 32-bit completion selection; preserve reset/recovery/complete/ack/retire/allocate priority and legacy parameter fallback; no added registers or cycles, no EDA run')
