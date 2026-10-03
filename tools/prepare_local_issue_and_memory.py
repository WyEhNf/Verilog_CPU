"""Source-only RS ownership and memory transaction pipeline preparation."""
from pathlib import Path
import re
from prepare_staged_frequency_candidate import change, prepare, ROOT


def local_rs_rows(t):
    t=change(t,'    parameter integer AGE_ORDER_MATRIX = 0,',
             '    parameter integer AGE_ORDER_MATRIX = 0,\n    parameter integer LOCAL_PAYLOAD_ROWS = 0,')
    fields=['target_live_mem','op_mem','pc_mem','rob_tag_mem','phys_rd_mem',
            'src1_value_mem','src1_tag_mem','src1_ready_mem',
            'src2_value_mem','src2_tag_mem','src2_ready_mem',
            'store_data_mem','metadata_mem','age_mem']
    for field in fields:
        pattern=r'    reg\s+([^;\n]*?)\b'+field+r' (\[0:ENTRIES-1\]);'
        m=re.search(pattern,t)
        if not m:
            raise ValueError('Missing RS storage declaration: '+field)
        dimensions=m.group(1)
        t=t[:m.start()]+f'    wire {dimensions}{field} [0:ENTRIES-1];\n    reg {dimensions}{field}_legacy [0:ENTRIES-1];'+t[m.end():]
    # The legacy sequential implementation remains available, with all its
    # payload destinations renamed. Only ONE implementation drives the public
    # row wires, selected at elaboration, never two writers to the same array.
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            occupancy_reg')
    sequential=t[start:]
    for field in fields:
        sequential=re.sub(r'\b'+field+r'\b',field+'_legacy',sequential)
    t=t[:start]+sequential
    # Raw grants still serve cached age-order updates. Wide payload consumers
    # use actual priced leaf drivers, avoiding a weak grant gate's fanout.
    t=change(t,'            reg [ALLOC_PAYLOAD_WIDTH-1:0] payload;', '''            wire [BE_WIDTH-1:0] payload_grants;
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(1)) grant_tree (
                .signal_i(grants),.views_o(payload_grants));
            reg [ALLOC_PAYLOAD_WIDTH-1:0] payload;''')
    t=change(t,'({ALLOC_PAYLOAD_WIDTH{grants[mux_lane]}} & alloc_lane_payload[mux_lane])',
             '({ALLOC_PAYLOAD_WIDTH{payload_grants[mux_lane]}} & alloc_lane_payload[mux_lane])')
    # Generated alias/row owners refer to the allocation payload once decoded.
    owner='''    genvar owner_row, owner_lane;
    generate for(owner_row=0;owner_row<ENTRIES;owner_row=owner_row+1) begin:g_payload_owner
        if(LOCAL_PAYLOAD_ROWS!=0 && ALLOC_STATIC_WRITE!=0) begin:g_local
            wire [BE_WIDTH-1:0] issued_here;
            for(owner_lane=0;owner_lane<BE_WIDTH;owner_lane=owner_lane+1) begin:g_issue
                assign issued_here[owner_lane]=issue_valid_o[owner_lane] && issue_ready_i[owner_lane] &&
                    issue_slot_o[owner_lane*SLOT_WIDTH +: SLOT_WIDTH]==owner_row;
            end
            wire [WAKE_WIDTH-1:0] match1,match2;
            wire [31:0] last1,last2;
            if(WAKE_MUX_IMPL!=0) begin:g_shared_wake
                assign match1=wake1_match[owner_row];assign match2=wake2_match[owner_row];
                assign last1=wake1_last[owner_row];assign last2=wake2_last[owner_row];
            end else begin:g_legacy_wake
                reg [31:0] value1,value2;
                integer wake_port;
                for(owner_lane=0;owner_lane<WAKE_WIDTH;owner_lane=owner_lane+1) begin:g_match
                    assign match1[owner_lane]=wake_valid_i[owner_lane] && wake_tag_i[owner_lane*TAG_WIDTH] &&
                        src1_tag_mem[owner_row][0] && wake_tag_i[owner_lane*TAG_WIDTH +: TAG_WIDTH]==src1_tag_mem[owner_row];
                    assign match2[owner_lane]=wake_valid_i[owner_lane] && wake_tag_i[owner_lane*TAG_WIDTH] &&
                        src2_tag_mem[owner_row][0] && wake_tag_i[owner_lane*TAG_WIDTH +: TAG_WIDTH]==src2_tag_mem[owner_row];
                end
                always @* begin
                    value1=0;value2=0;
                    for(wake_port=0;wake_port<WAKE_WIDTH;wake_port=wake_port+1) begin
                        if(match1[wake_port]) value1=wake_value_i[wake_port*32 +: 32];
                        if(match2[wake_port]) value2=wake_value_i[wake_port*32 +: 32];
                    end
                end
                assign last1=value1;assign last2=value2;
            end
            rv32_rs_payload_row #(.OP_WIDTH(OP_WIDTH),.TAG_WIDTH(TAG_WIDTH),
                .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH),.STORE_DATA_WIDTH(STORE_DATA_WIDTH),
                .METADATA_WIDTH(METADATA_WIDTH),.AGE_WIDTH(AGE_WIDTH),
                .PAYLOAD_WIDTH(ALLOC_PAYLOAD_WIDTH)) row (
                .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_valid_i),
                .kill_i(flush_kill_mask_i[owner_row]),.valid_i(valid_mem[owner_row]),.issue_i(|issued_here),
                .alloc_i(alloc_row_write[owner_row]),.payload_i(alloc_row_payload[owner_row]),
                .wake1_i(|match1),.wake2_i(|match2),.wake1_value_i(last1),.wake2_value_i(last2),
                .target_live_o(target_live_mem[owner_row]),.op_o(op_mem[owner_row]),.pc_o(pc_mem[owner_row]),
                .rob_tag_o(rob_tag_mem[owner_row]),.phys_rd_o(phys_rd_mem[owner_row]),
                .src1_value_o(src1_value_mem[owner_row]),.src1_tag_o(src1_tag_mem[owner_row]),.src1_ready_o(src1_ready_mem[owner_row]),
                .src2_value_o(src2_value_mem[owner_row]),.src2_tag_o(src2_tag_mem[owner_row]),.src2_ready_o(src2_ready_mem[owner_row]),
                .store_data_o(store_data_mem[owner_row]),.metadata_o(metadata_mem[owner_row]),.age_o(age_mem[owner_row]));
        end else begin:g_legacy
'''
    owner+=''.join(f'            assign {field}[owner_row]={field}_legacy[owner_row];\n' for field in fields)
    owner+='''        end
    end endgenerate

'''
    t=change(t,'    // Allocate a contiguous prefix and choose the oldest ready entries for',
             owner+'    // Allocate a contiguous prefix and choose the oldest ready entries for')
    t+='''
// Each row owns its final data writes. Wide metadata has no reset/flush
// feedback mux after its qualified and priced local write driver.
module rv32_rs_payload_row #(
    parameter integer OP_WIDTH=6,TAG_WIDTH=17,PHYS_ADDR_WIDTH=6,
    parameter integer STORE_DATA_WIDTH=32,METADATA_WIDTH=70,AGE_WIDTH=8,
    parameter integer PAYLOAD_WIDTH=272
) (
    input wire clk_i,reset_i,flush_i,kill_i,valid_i,issue_i,alloc_i,
    input wire [PAYLOAD_WIDTH-1:0] payload_i,
    input wire wake1_i,wake2_i,
    input wire [31:0] wake1_value_i,wake2_value_i,
    output reg target_live_o,
    output reg [OP_WIDTH-1:0] op_o,
    output reg [31:0] pc_o,src1_value_o,src2_value_o,
    output reg [TAG_WIDTH-1:0] rob_tag_o,src1_tag_o,src2_tag_o,
    output reg [PHYS_ADDR_WIDTH-1:0] phys_rd_o,
    output reg src1_ready_o,src2_ready_o,
    output reg [STORE_DATA_WIDTH-1:0] store_data_o,
    output reg [METADATA_WIDTH-1:0] metadata_o,
    output reg [AGE_WIDTH-1:0] age_o
);
    wire new_live,new_ready1,new_ready2;
    wire [OP_WIDTH-1:0] new_op;
    wire [31:0] new_pc,new_value1,new_value2;
    wire [TAG_WIDTH-1:0] new_tag,new_tag1,new_tag2;
    wire [PHYS_ADDR_WIDTH-1:0] new_phys;
    wire [STORE_DATA_WIDTH-1:0] new_store;
    wire [METADATA_WIDTH-1:0] new_metadata;
    wire [AGE_WIDTH-1:0] new_age;
    assign {new_live,new_op,new_pc,new_tag,new_phys,new_value1,new_tag1,new_ready1,
            new_value2,new_tag2,new_ready2,new_store,new_metadata,new_age}=payload_i;
    wire allocation=!reset_i && !flush_i && alloc_i;
    wire wake_allowed=!reset_i && valid_i && (!flush_i || !kill_i);
    wire wake1_write=wake_allowed && !src1_ready_o && wake1_i;
    wire wake2_write=wake_allowed && !src2_ready_o && wake2_i;
    wire [5:0] alloc_views;
    wire src1_write,src2_write;
    rv32_frequency_control_tree #(.LEAVES(6)) allocation_tree (
        .signal_i(allocation),.views_o(alloc_views));
    rv32_frequency_control_tree #(.LEAVES(1)) value1_tree (
        .signal_i(allocation || wake1_write),.views_o(src1_write));
    rv32_frequency_control_tree #(.LEAVES(1)) value2_tree (
        .signal_i(allocation || wake2_write),.views_o(src2_write));
    // Allocation wins over a simultaneous wake, exactly as the old NBA order.
    always @(posedge clk_i) begin
        if(alloc_views[0]) {op_o,pc_o,rob_tag_o,phys_rd_o,store_data_o,metadata_o}<=
            {new_op,new_pc,new_tag,new_phys,new_store,new_metadata};
        if(alloc_views[1]) src1_tag_o<=new_tag1;
        if(alloc_views[2]) src2_tag_o<=new_tag2;
        if(src1_write) src1_value_o<=alloc_views[3]?new_value1:wake1_value_i;
        if(src2_write) src2_value_o<=alloc_views[4]?new_value2:wake2_value_i;
        if(reset_i) begin
            target_live_o<=0;src1_ready_o<=0;src2_ready_o<=0;age_o<=0;
        end else begin
            if(alloc_views[5]) begin
                target_live_o<=new_live;src1_ready_o<=new_ready1;src2_ready_o<=new_ready2;age_o<=new_age;
            end else begin
                if(wake1_write) src1_ready_o<=1;
                if(wake2_write) src2_ready_o<=1;
            end
            if((flush_i && kill_i) || (!flush_i && issue_i)) target_live_o<=0;
        end
    end
endmodule
'''
    return t


def enable_local_rs(t):
    return change(t,'.AGE_ORDER_MATRIX(1), .ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE),',
                  '.AGE_ORDER_MATRIX(1), .LOCAL_PAYLOAD_ROWS(1), .ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE),')


def lsq_request_pipeline(t):
    t=change(t,'    parameter integer STORE_ADDRESS_PROBE = 0,',
             '    parameter integer STORE_ADDRESS_PROBE = 0,\n    parameter integer REQUEST_PIPELINE = 0,')
    insert='''    // Selection and forwarding belong to separate clock stages. A stalled
    // load also retains the forwarding snapshot, rather than re-evaluating
    // its public request as older stores depart the queue.
    reg selection_valid,selection_load,selection_unsigned;
    reg [SLOT_WIDTH-1:0] selection_slot;
    reg [TAG_WIDTH-1:0] selection_lsq_tag;
    reg [ROB_TAG_WIDTH-1:0] selection_rob_tag;
    reg [31:0] selection_addr,selection_store_data;
    reg [1:0] selection_size;
    reg [3:0] selection_store_mask;
    reg forwarding_hold_valid;
    reg [3:0] forwarding_hold_mask;
    reg [31:0] forwarding_hold_data;
    wire selection_live=selection_valid && tag_matches_slot(selection_lsq_tag,selection_slot) &&
        !request_sent_mem[selection_slot] && !complete_mem[selection_slot] && !response_wait_mem[selection_slot];
    wire selection_discard=selection_valid && !selection_live;
    wire [SLOT_WIDTH-1:0] selected_slot=(REQUEST_PIPELINE!=0)?selection_slot:pick_slot[1];
    wire [31:0] selected_addr=(REQUEST_PIPELINE!=0)?selection_addr:pick_addr[1];
    wire [SLOT_WIDTH-1:0] selected_age=selected_slot-head_reg;
    wire [1:0] selected_size=(REQUEST_PIPELINE!=0)?selection_size:size_mem[pick_slot[1]];
    wire selected_unsigned=(REQUEST_PIPELINE!=0)?selection_unsigned:unsigned_mem[pick_slot[1]];
    wire selected_load=(REQUEST_PIPELINE!=0)?selection_load:load_mem[pick_slot[1]];
    wire [3:0] selected_store_mask=(REQUEST_PIPELINE!=0)?selection_store_mask:mask_mem[pick_slot[1]];
    wire [31:0] selected_store_data=(REQUEST_PIPELINE!=0)?selection_store_data:data_mem[pick_slot[1]];
    wire [ROB_TAG_WIDTH-1:0] selected_rob_tag=(REQUEST_PIPELINE!=0)?selection_rob_tag:rob_tag_mem[pick_slot[1]];
    wire [TAG_WIDTH-1:0] selected_lsq_tag=(REQUEST_PIPELINE!=0)?selection_lsq_tag:
        make_lsq_tag(pick_slot[1],generation_mem[pick_slot[1]]);
    wire selection_done=selection_live && (request_fire ||
        (selection_load && candidate_found && ((fwd_mask & target_mask)==target_mask)));
    wire selection_input_fire=(REQUEST_PIPELINE!=0) && !reset_i && !flush_i && !recovery_valid_i &&
        (!selection_valid || selection_discard || selection_done) && pick_valid[1];
    wire [4:0] selection_write_views;
    rv32_frequency_control_tree #(.LEAVES(5)) selection_write_tree (
        .signal_i(selection_input_fire),.views_o(selection_write_views));
    wire forwarding_hold_write=(REQUEST_PIPELINE!=0) && candidate_found && selected_load &&
        dcache_req_valid_o && !dcache_req_ready_i && !forwarding_hold_valid;
    wire forwarding_payload_write;
    rv32_frequency_control_tree #(.LEAVES(1)) forwarding_hold_tree (
        .signal_i(forwarding_hold_write),.views_o(forwarding_payload_write));
    wire [ROB_SLOT_WIDTH-1:0] selection_rob_age=selection_rob_tag[3 +: ROB_SLOT_WIDTH]-recovery_head_i;
    wire [ROB_SLOT_WIDTH-1:0] selection_branch_age=recovery_tag_i[3 +: ROB_SLOT_WIDTH]-recovery_head_i;
    wire selection_recovery_kill=selection_valid &&
        !(store_mem[selection_slot] && store_commit_mem[selection_slot]) &&
        !(load_mem[selection_slot] && retired_mem[selection_slot]) &&
        selection_rob_age>selection_branch_age && selection_rob_age<recovery_occupancy_i;
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin selection_valid<=0;forwarding_hold_valid<=0;end
        else if(recovery_valid_i) begin
            if(selection_recovery_kill) begin selection_valid<=0;forwarding_hold_valid<=0;end
        end else begin
            if(selection_input_fire) selection_valid<=1;
            else if(selection_done || selection_discard) selection_valid<=0;
            if(selection_input_fire || selection_done || selection_discard) forwarding_hold_valid<=0;
            else if(forwarding_hold_write) forwarding_hold_valid<=1;
        end
        if(selection_write_views[0]) begin
            selection_slot<=pick_slot[1];
            selection_lsq_tag<=make_lsq_tag(pick_slot[1],generation_mem[pick_slot[1]]);
            selection_rob_tag<=rob_tag_mem[pick_slot[1]];
        end
        if(selection_write_views[1]) selection_addr<=pick_addr[1];
        if(selection_write_views[2]) begin
            selection_load<=load_mem[pick_slot[1]];selection_size<=size_mem[pick_slot[1]];
            selection_unsigned<=unsigned_mem[pick_slot[1]];
        end
        if(selection_write_views[3]) selection_store_mask<=mask_mem[pick_slot[1]];
        if(selection_write_views[4]) selection_store_data<=data_mem[pick_slot[1]];
        if(forwarding_payload_write) begin forwarding_hold_mask<=fwd_mask;forwarding_hold_data<=fwd_data;end
    end

'''
    t=change(t,'    genvar age_slot;\n',insert+'    genvar age_slot;\n')
    # Forwarding stage consumes the registered request; arbitration still
    # consumes the current LSQ table and excludes the held selection.
    start=t.index('            assign store_overlap[age_slot] =')
    end=t.index('    // A load is blocked',start)
    part=t[start:end].replace('pick_age[1]','selected_age').replace('pick_addr[1]','selected_addr').replace('size_mem[pick_slot[1]]','selected_size')
    t=t[:start]+part+t[end:]
    t=change(t,'                valid_mem[request_slot] &&\n                ((load_mem[request_slot]',
             '''                valid_mem[request_slot] &&
                !(REQUEST_PIPELINE!=0 && selection_valid && selection_slot==request_slot) &&
                ((load_mem[request_slot]''')
    t=change(t,'''        candidate_found = pick_valid[1];
        candidate = pick_valid[1] ? pick_slot[1] : 0;
        candidate_age = pick_valid[1] ? pick_age[1] : LSQ_ENTRIES + 1;''', '''        candidate_found = (REQUEST_PIPELINE!=0)?selection_live:pick_valid[1];
        candidate = candidate_found ? selected_slot : 0;
        candidate_age = candidate_found ? selected_age : LSQ_ENTRIES + 1;''')
    start=t.index("        dcache_req_valid_o = 1'b0;")
    end=t.index('        // A fully covered load never touches the cache.',start)
    part=t[start:end].replace('pick_addr[1]','selected_addr').replace('if (load_mem[candidate])','if (selected_load)')
    part=part.replace('access_mask(size_mem[candidate])','access_mask(selected_size)')
    part=part.replace('fwd_mask = tree_forward_mask;',
                      'fwd_mask = (REQUEST_PIPELINE!=0 && forwarding_hold_valid)?forwarding_hold_mask:tree_forward_mask;')
    part=part.replace('fwd_data = tree_forward_data;',
                      'fwd_data = (REQUEST_PIPELINE!=0 && forwarding_hold_valid)?forwarding_hold_data:tree_forward_data;')
    part=part.replace('size_mem[candidate]','selected_size').replace('unsigned_mem[candidate]','selected_unsigned')
    part=part.replace('mask_mem[candidate]','selected_store_mask').replace('data_mem[candidate]','selected_store_data')
    part=part.replace('rob_tag_mem[candidate]','selected_rob_tag')
    part=part.replace('make_lsq_tag(candidate, generation_mem[candidate])','selected_lsq_tag')
    t=t[:start]+part+t[end:]
    t=change(t,'''                        fwd_data, size_mem[candidate], unsigned_mem[candidate]);''',
             '''                        fwd_data, selected_size, selected_unsigned);''')
    return t


def enable_lsq_pipeline(t):
    return change(t,'.STORE_ADDRESS_PROBE(EARLY_STORE_ADDRESS == 2), .TAG_WIDTH(TAG_WIDTH)',
                  '.STORE_ADDRESS_PROBE(EARLY_STORE_ADDRESS == 2), .REQUEST_PIPELINE(1), .TAG_WIDTH(TAG_WIDTH)')


def icache_request_boundary(t):
    t=change(t,'    parameter integer LOCAL_RESPONSE_READY = 0,',
             '    parameter integer LOCAL_RESPONSE_READY = 0,\n    parameter integer REQUEST_PIPELINE = 0,')
    body_start=t.index('    reg [CACHE_LINES-1:0] valid_bits;')
    body_end=t.index('endmodule',body_start)
    body=t[body_start:body_end]
    for old,new in [('if_req_valid_i','lookup_req_valid'),('if_req_ready_o','lookup_req_ready'),
                    ('if_req_pc_i','lookup_req_pc'),('if_req_epoch_i','lookup_req_epoch')]:
        body=re.sub(r'\b'+old+r'\b',new,body)
    front='''    wire lookup_req_valid,lookup_req_ready;
    wire [31:0] lookup_req_pc;
    wire [EPOCH_WIDTH-1:0] lookup_req_epoch;
    generate if(REQUEST_PIPELINE!=0) begin:g_request_pipeline
        rv32_icache_query_queue #(.EPOCH_WIDTH(EPOCH_WIDTH)) requests (
            .clk_i(clk_i),.reset_i(reset_i),.current_epoch_i(current_epoch_i),
            .valid_i(if_req_valid_i),.ready_o(if_req_ready_o),.pc_i(if_req_pc_i),.epoch_i(if_req_epoch_i),
            .valid_o(lookup_req_valid),.ready_i(lookup_req_ready),.pc_o(lookup_req_pc),.epoch_o(lookup_req_epoch));
    end else begin:g_direct_request
        assign lookup_req_valid=if_req_valid_i;assign if_req_ready_o=lookup_req_ready;
        assign lookup_req_pc=if_req_pc_i;assign lookup_req_epoch=if_req_epoch_i;
    end endgenerate

'''
    t=t[:body_start]+front+body+t[body_end:]
    # Renaming parent signals must not rename child module port identifiers.
    t=t.replace('.lookup_req_pc(lookup_req_pc)', '.if_req_pc_i(lookup_req_pc)')
    t=t.replace('.lookup_req_epoch(lookup_req_epoch)', '.if_req_epoch_i(lookup_req_epoch)')
    # Parallel tag match still needs local electrical query domains after the
    # new FF boundary. Price real cells; do not rely on duplicate assigns.
    t=change(t,'    genvar match_row;', '''    wire [4*32-1:0] demand_pc_views,prefetch_pc_views,control_pc_views;
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) demand_query_tree (
        .signal_i(lookup_req_pc),.views_o(demand_pc_views));
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) prefetch_query_tree (
        .signal_i(prefetch_next_line),.views_o(prefetch_pc_views));
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) control_query_tree (
        .signal_i(control_target),.views_o(control_pc_views));
    genvar match_row;''')
    start=t.index('        if (TAG_MATCH_PARALLEL != 0) begin:g_parallel')
    end=t.index('        end else begin:g_disabled',start)
    t=t[:start]+'''        if (TAG_MATCH_PARALLEL != 0) begin:g_parallel
            localparam integer DOMAIN=(match_row*4)/CACHE_LINES;
            wire [31:0] demand_pc=demand_pc_views[DOMAIN*32 +: 32];
            wire [31:0] prefetch_pc=prefetch_pc_views[DOMAIN*32 +: 32];
            wire [31:0] control_pc=control_pc_views[DOMAIN*32 +: 32];
            wire demand_hit=valid_bits[match_row] &&
                demand_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                tag_mem[match_row]==demand_pc[31:CACHE_SET_WIDTH+4];
            assign demand_match_way0[match_row]=(match_row%CACHE_WAYS==0) && demand_hit;
            assign demand_match_way1[match_row]=(match_row%CACHE_WAYS==1) && demand_hit;
            assign prefetch_match_rows[match_row]=valid_bits[match_row] &&
                prefetch_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                tag_mem[match_row]==prefetch_pc[31:CACHE_SET_WIDTH+4];
            assign control_match_rows[match_row]=valid_bits[match_row] &&
                control_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                tag_mem[match_row]==control_pc[31:CACHE_SET_WIDTH+4];
'''+t[end:]
    t+='''
// Two request slots decouple front-end ready from tag/MSHR/response logic.
// Epoch-stale requests drain independently of lookup readiness.
module rv32_icache_query_queue #(parameter integer EPOCH_WIDTH=4) (
    input wire clk_i,reset_i,
    input wire [EPOCH_WIDTH-1:0] current_epoch_i,
    input wire valid_i,
    output wire ready_o,
    input wire [31:0] pc_i,
    input wire [EPOCH_WIDTH-1:0] epoch_i,
    output wire valid_o,
    input wire ready_i,
    output wire [31:0] pc_o,
    output wire [EPOCH_WIDTH-1:0] epoch_o
);
    reg [1:0] count;
    reg read_slot,write_slot;
    reg [32+EPOCH_WIDTH-1:0] payload [0:1];
    wire read_local;
    rv32_frequency_control_tree #(.LEAVES(1)) read_tree (
        .signal_i(read_slot),.views_o(read_local));
    assign {pc_o,epoch_o}=read_local?payload[1]:payload[0];
    wire stale=count!=0 && epoch_o!=current_epoch_i;
    assign ready_o=!reset_i && count<2;
    assign valid_o=!reset_i && count!=0 && !stale;
    wire push=valid_i && ready_o;
    wire pop=!reset_i && (stale || (valid_o && ready_i));
    genvar queue_row;
    generate for(queue_row=0;queue_row<2;queue_row=queue_row+1) begin:g_row
        wire write_local;
        rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
            .signal_i(push && write_slot==queue_row),.views_o(write_local));
        always @(posedge clk_i) if(write_local) payload[queue_row]<={pc_i,epoch_i};
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i) begin count<=0;read_slot<=0;write_slot<=0;end
        else begin
            count<=count+push-pop;
            if(pop) read_slot<=!read_slot;
            if(push) write_slot<=!write_slot;
        end
    end
endmodule
'''
    return t


def enable_icache_pipeline(t):
    return change(t,'.LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY),',
                  '.LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY), .REQUEST_PIPELINE(1),')


def dcache_query_field_ownership(t):
    declarations='''        wire [8:0] query_write_views;
        rv32_frequency_control_tree #(.LEAVES(9)) query_write_tree (
            .signal_i(input_fire),.views_o(query_write_views));
        // input_fire already includes !reset and !flush. These data fields
        // have one local write owner without a later global control mux.
        always @(posedge clk_i) begin
            if(query_write_views[0]) query_wdata[0 +: 32]<=dcache_req_wdata_i[0 +: 32];
            if(query_write_views[1]) query_wdata[32 +: 32]<=dcache_req_wdata_i[32 +: 32];
            if(query_write_views[2]) query_wdata[64 +: 32]<=dcache_req_wdata_i[64 +: 32];
            if(query_write_views[3]) query_wdata[96 +: 32]<=dcache_req_wdata_i[96 +: 32];
            if(query_write_views[4]) begin query_rob<=dcache_req_rob_tag_i;query_lsq<=dcache_req_lsq_tag_i;end
            if(query_write_views[5]) query_addr<=dcache_req_addr_i;
            if(query_write_views[6] && REGISTERED_INDEX!=0) begin
                query_request_index<=cache_index(dcache_req_addr_i);
                query_prefetch_index<=cache_index(input_prefetch_line);
            end
            if(query_write_views[7]) begin
                query_load<=dcache_req_is_load_i;query_store<=dcache_req_is_store_i;
                query_size<=dcache_req_size_i;query_unsigned<=dcache_req_unsigned_i;
            end
            if(query_write_views[8]) query_mask<=dcache_req_mask_i;
        end
'''
    t=change(t,'        integer forward_way;\n',declarations+'        integer forward_way;\n')
    old='''                    query_load <= dcache_req_is_load_i;
                    query_store <= dcache_req_is_store_i;
                    query_addr <= dcache_req_addr_i;
                    // Follow exactly the same acceptance/hold/warm-reset
                    // ownership as query_addr. Invalid payload stays undefined.
                    if (REGISTERED_INDEX != 0) begin
                        query_request_index <= cache_index(dcache_req_addr_i);
                        query_prefetch_index <= cache_index(input_prefetch_line);
                    end
                    query_size <= dcache_req_size_i;
                    query_unsigned <= dcache_req_unsigned_i;
                    query_mask <= dcache_req_mask_i;
                    query_wdata <= dcache_req_wdata_i;
                    query_rob <= dcache_req_rob_tag_i;
                    query_lsq <= dcache_req_lsq_tag_i;
'''
    return change(t,old,'')


if __name__=='__main__':
    prepare('I_local_rs_storage',ROOT/'H_cached_issue_age',
            {'rtl/backend/rv32_reservation_station.v':local_rs_rows,
             'rtl/backend/rv32_backend_joint.v':enable_local_rs},
            'H plus local per-row RS payload ownership and final qualified write drivers, shared wake comparisons and priced wide grant domains')
