"""Prepare source-only architectural frequency candidates; never run EDA/tests."""
import difflib
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path('F:/CPU2026Candidates/frequency_research_20261003')
BASE = Path('F:/CPU2026CourseRuns/current_adopted_20261003/source')


def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected exactly one source anchor: {old[:100]!r}')
    return text.replace(old, new, 1)


def staged_rob(t):
    t = change(t, '    parameter integer CHECKPOINT_IMPL = 0,', '''    parameter integer CHECKPOINT_IMPL = 0,
    // Preview captures a recovery transaction; apply is a later clock edge.
    // Default 0 preserves the standalone legacy interface behavior.
    parameter integer STAGED_RECOVERY = 0,''')
    t = change(t, '    output wire                         recovery_accept_o,', '''    input  wire                         recovery_apply_i,
    input  wire                         recovery_hold_i,
    output wire                         recovery_preview_valid_o,
    output wire                         recovery_accept_o,''')
    t = change(t, '''    reg recovery_found;
    wire [5:0] recovery_domains;
    rv32_frequency_control_tree #(.LEAVES(6)) recovery_tree (
        .signal_i(recovery_found),.views_o(recovery_domains));
    assign recovery_accept_o=recovery_domains[0];
    assign redirect_valid_o=recovery_domains[1];
    assign checkpoint_restore_valid_o=recovery_domains[2];''', '''    reg recovery_found;
    reg recovery_saved_valid;
    reg [SLOT_WIDTH-1:0] recovery_saved_slot, recovery_saved_age;
    reg [ROB_ENTRIES-1:0] recovery_saved_kill;
    wire [ROB_ENTRIES-1:0] recovery_preview_kill;
    wire [SLOT_WIDTH-1:0] apply_slot = STAGED_RECOVERY ? recovery_saved_slot : chosen_slot;
    wire [SLOT_WIDTH-1:0] apply_age = STAGED_RECOVERY ? recovery_saved_age : chosen_age;
    wire recovery_apply = STAGED_RECOVERY ?
        (recovery_apply_i && recovery_saved_valid) : recovery_found;
    wire recovery_hold = STAGED_RECOVERY && recovery_hold_i;
    wire [5:0] recovery_domains;
    wire [2:0] recovery_preview_domains;
    rv32_frequency_control_tree #(.LEAVES(6)) recovery_tree (
        .signal_i(recovery_apply),.views_o(recovery_domains));
    rv32_frequency_control_tree #(.LEAVES(3)) recovery_preview_tree (
        .signal_i(recovery_found),.views_o(recovery_preview_domains));
    assign recovery_preview_valid_o=recovery_preview_domains[0];
    assign recovery_accept_o=recovery_domains[0];
    assign redirect_valid_o=STAGED_RECOVERY ? recovery_preview_domains[1] : recovery_domains[1];
    assign checkpoint_restore_valid_o=recovery_domains[2];
    genvar recovery_row;
    generate for(recovery_row=0;recovery_row<ROB_ENTRIES;recovery_row=recovery_row+1) begin:g_recovery_descriptor
        wire [SLOT_WIDTH-1:0] relative_age = recovery_row-head_recovery_index;
        assign recovery_preview_kill[recovery_row] = valid_mem[recovery_row] &&
            relative_age>chosen_age && relative_age<occupancy_reg;
    end endgenerate
    // Allocation and commit are held between preview and apply, so these
    // physical slot identities cannot be reused while the mask is pending.
    always @(posedge clk_i) begin
        if(reset_i) recovery_saved_valid<=1'b0;
        else if(recovery_domains[5] || !recovery_hold) recovery_saved_valid<=1'b0;
        else if(recovery_preview_domains[0] && !recovery_saved_valid) begin
            recovery_saved_valid<=1'b1;
            recovery_saved_slot<=chosen_slot;
            recovery_saved_age<=chosen_age;
            recovery_saved_kill<=recovery_preview_kill;
        end
    end''')
    t = change(t, 'assign head_next = recovery_domains[3] ? head_reg :',
               'assign head_next = (recovery_domains[3] || recovery_hold) ? head_reg :')
    t = change(t, 'assign alloc_ready_o = (alloc_count_o != 0) && !recovery_domains[3];',
               'assign alloc_ready_o = (alloc_count_o != 0) && !recovery_domains[3] && !recovery_hold;')
    t = change(t, '        prefix_open = 1\'b1;\n        allocation_count = 0;',
               "        prefix_open = !recovery_hold;\n        allocation_count = 0;")
    t = t.replace('reclaim_eligible[reclaim_entry] = recovery_domains[4]',
                  'reclaim_eligible[reclaim_entry] = recovery_preview_domains[2]')
    t = change(t, '        if (recovery_domains[4]) begin\n            redirect_pc_o',
               '        if (recovery_preview_domains[2]) begin\n            redirect_pc_o')
    t = change(t, 'if (!recovery_domains[5] && !halted_o && !error_o)',
               'if (!recovery_domains[5] && !recovery_hold && !halted_o && !error_o)')
    t = change(t, '            branch_age = chosen_age;', '            branch_age = apply_age;')
    t = change(t, 'if (valid_mem[reset_slot] && (younger_age > branch_age) && (younger_age < occupancy_reg)) begin',
               '''if (STAGED_RECOVERY ? recovery_saved_kill[reset_slot] :
                    (valid_mem[reset_slot] && (younger_age > branch_age) && (younger_age < occupancy_reg))) begin''')
    t = change(t, 'tail_reg <= advance_slot(chosen_slot[SLOT_WIDTH-1:0], 1);',
               'tail_reg <= advance_slot(apply_slot, 1);')
    return t


def staged_backend(t):
    t = change(t, '    reg branch_pending;','''    // Front-end redirect is issued during preview. Backend recovery is a
    // registered transaction applied on the following edge.
    reg branch_pending;
    reg recovery_descriptor_valid;
    reg [CHECK_RAT_WIDTH-1:0] recovery_descriptor_rat;
    reg [PHYS_REGS-1:0] recovery_descriptor_reclaim;
    reg [FREE_COUNT_WIDTH-1:0] recovery_descriptor_reclaim_count;
    reg [ROB_SLOT_WIDTH-1:0] recovery_descriptor_head;
    reg [ROB_COUNT_WIDTH-1:0] recovery_descriptor_occupancy;
    reg [RS_ENTRIES-1:0] recovery_descriptor_rs_kill;
    wire rob_recovery_preview;
    wire recovery_preview_fire = branch_pending && rob_recovery_preview &&
        !recovery_descriptor_valid && !flush_i;
    wire [3:0] branch_busy_domains;
    wire [3:0] recovery_capture_domains;
    rv32_frequency_control_tree #(.LEAVES(4)) branch_busy_tree (
        .signal_i(branch_pending),.views_o(branch_busy_domains));
    rv32_frequency_control_tree #(.LEAVES(4)) recovery_capture_tree (
        .signal_i(recovery_preview_fire),.views_o(recovery_capture_domains));
    wire [6*ROB_SLOT_WIDTH-1:0] recovery_head_views;
    rv32_frequency_control_tree #(.WIDTH(ROB_SLOT_WIDTH),.LEAVES(6)) recovery_head_tree (
        .signal_i(recovery_descriptor_head),.views_o(recovery_head_views));''')
    t = change(t, '    reg [RS_ENTRIES-1:0] rs_flush_kill_mask;',
               '    reg [RS_ENTRIES-1:0] rs_flush_kill_mask;\n    reg [RS_ENTRIES-1:0] rs_preview_kill_mask;')
    # Resolve capacity/issue gating from the pending FF, never late preview.
    t = t.replace('!recovery_domains[0]', '!branch_busy_domains[0]')
    t = t.replace('!recovery_domains[1]', '!branch_busy_domains[1]')
    t = change(t, '.issue_valid_i(!recovery_domains[4] &&',
               '.issue_valid_i(!branch_busy_domains[2] &&')
    t = change(t, '.COMMIT_BANKED_READ(ROB_COMMIT_BANKED_READ), .ALLOC_BANKED_WRITE',
               '.STAGED_RECOVERY(1), .COMMIT_BANKED_READ(ROB_COMMIT_BANKED_READ), .ALLOC_BANKED_WRITE')
    t = change(t, '.recovery_accept_o(rob_recovery_accept_source),', '''.recovery_apply_i(recovery_descriptor_valid), .recovery_hold_i(branch_busy_domains[3]),
        .recovery_preview_valid_o(rob_recovery_preview), .recovery_accept_o(rob_recovery_accept_source),''')
    t = change(t, 'assign redirect_valid_o = rob_redirect_valid;',
               'assign redirect_valid_o = recovery_preview_fire;')
    # Store only the reclamation delta, merge with CURRENT free state at apply.
    t = change(t, 'recovery_free_bitmap = free_bitmap_state | rob_recovery_reclaim_bitmap;',
               'recovery_free_bitmap = free_bitmap_state | recovery_descriptor_reclaim;')
    t = change(t, 'recovery_free_count = free_count + rob_recovery_reclaim_count;',
               'recovery_free_count = free_count + recovery_descriptor_reclaim_count;')
    t = change(t, '.restore_rat_i(recovery_rat_state)', '.restore_rat_i(recovery_descriptor_rat)')
    start = t.index('    // External flushes clear the station.')
    end = t.index('    // Completions may be queued', start)
    part = t[start:end].replace('rs_flush_kill_mask','rs_preview_kill_mask').replace('recovery_domains[2]', 'rob_recovery_preview')
    part += '''    always @* begin
        rs_flush_kill_mask = flush_i ? {RS_ENTRIES{1'b1}} : recovery_descriptor_rs_kill;
    end

'''
    t = t[:start] + part + t[end:]
    # Queued completion slots can be reused while a descriptor is pending.
    # Re-evaluate CURRENT tags against the saved boundary at apply, rather
    # than registering a mask of queue slot positions.
    start = t.index('    // Completions may be queued')
    end = t.index('    // Rename and PRF', start)
    part = t[start:end].replace('rob_head_views[2*ROB_SLOT_WIDTH', 'recovery_head_views[2*ROB_SLOT_WIDTH').replace('>= rob_occupancy', '>= recovery_descriptor_occupancy')
    t = t[:start]+part+t[end:]
    start = t.index('        producer_recovery_rob_slot = 0;')
    end = t.index('    always @* begin\n        alu_exec_ready_r', start)
    part = t[start:end].replace('rob_head_views[4*ROB_SLOT_WIDTH', 'recovery_head_views[4*ROB_SLOT_WIDTH').replace('rob_head_views[5*ROB_SLOT_WIDTH', 'recovery_head_views[5*ROB_SLOT_WIDTH').replace('>= rob_occupancy', '>= recovery_descriptor_occupancy')
    t = t[:start]+part+t[end:]
    t = change(t, '.head_i(rob_head_views[5*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]),\n                .valid_i',
               '.head_i(recovery_head_views[5*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]),\n                .valid_i')
    t = change(t, '.recovery_head_i(rob_head), .recovery_occupancy_i({{(16-ROB_COUNT_WIDTH){1\'b0}}, rob_occupancy})',
               '.recovery_head_i(recovery_head_views[3*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]), .recovery_occupancy_i({{(16-ROB_COUNT_WIDTH){1\'b0}}, recovery_descriptor_occupancy})')
    # Capture descriptor payload outside validity reset/flush muxes. Every
    # valid transaction writes all fields before it can be applied.
    position = t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            branch_pending')
    t = t[:position]+'''    always @(posedge clk_i) begin
        if(reset_i || flush_i) recovery_descriptor_valid<=1'b0;
        else if(recovery_domains[7]) recovery_descriptor_valid<=1'b0;
        else if(recovery_capture_domains[0]) recovery_descriptor_valid<=1'b1;
        if(recovery_capture_domains[1]) recovery_descriptor_rat<=recovery_rat_state;
        if(recovery_capture_domains[2]) begin
            recovery_descriptor_reclaim<=rob_recovery_reclaim_bitmap;
            recovery_descriptor_reclaim_count<=rob_recovery_reclaim_count;
        end
        if(recovery_capture_domains[3]) begin
            recovery_descriptor_head<=rob_head_views[0 +: ROB_SLOT_WIDTH];
            recovery_descriptor_occupancy<=rob_occupancy;
            recovery_descriptor_rs_kill<=rs_preview_kill_mask;
        end
    end

'''+t[position:]
    t = change(t, '''            if (recovery_domains[7] && branch_pending) begin
                if (PREDICTOR_META != 0)
                    branch_recovery_history_o <= (branch_pending_kind == `RV32IM_PRED_BRANCH) ?
                        {rob_pred_metadata_mem[branch_pending_tag[3 +: ROB_SLOT_WIDTH]][14:8],
                         branch_pending_taken} :
                        rob_pred_metadata_mem[branch_pending_tag[3 +: ROB_SLOT_WIDTH]][15:8];''', '''            if (flush_i || (branch_pending && !recovery_descriptor_valid && !rob_recovery_preview)) begin
                branch_pending <= 1'b0;
            end else if (recovery_domains[7] && branch_pending) begin''')
    t = change(t, '''if (!branch_capture_found && alu_exec_valid[branch_lane] &&
                        alu_exec_redirect_valid[branch_lane]) begin''', '''if (!flush_i && !branch_capture_found && alu_exec_valid[branch_lane] &&
                        alu_exec_ready[branch_lane] && branch_training_live[branch_lane] &&
                        alu_exec_redirect_valid[branch_lane]) begin''')
    t = change(t, '                        branch_capture_found = 1;', '''                        // History must be ready BEFORE the early front-end
                        // redirect samples it, not updated on backend apply.
                        if(PREDICTOR_META != 0)
                            branch_recovery_history_o <=
                                (((RS_ISSUE_METADATA != 0) ? alu_exec_pred_kind[branch_lane*2 +: 2] :
                                  rob_pred_kind_mem[alu_exec_tag[branch_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]]) == `RV32IM_PRED_BRANCH) ?
                                {rob_pred_metadata_mem[alu_exec_tag[branch_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]][14:8],
                                 alu_exec_branch_taken[branch_lane]} :
                                rob_pred_metadata_mem[alu_exec_tag[branch_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]][15:8];
                        branch_capture_found = 1;''')
    return t


def prepare(name, parent, transforms, description):
    out=ROOT/name
    if out.exists():
        raise FileExistsError(out)
    manifest=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    for name_in in manifest['source_sha256']:
        target=out/name_in
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(parent/name_in,target)
    for name_in,transform in transforms.items():
        target=out/name_in
        target.write_text(transform(target.read_text(encoding='utf-8')),encoding='utf-8',newline='\n')
    source={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in manifest['source_sha256']}
    changed=[n for n in source if source[n]!=hashlib.sha256((BASE/n).read_bytes()).hexdigest()]
    patch=''.join(''.join(difflib.unified_diff((BASE/n).read_text(encoding='utf-8').splitlines(keepends=True),
                 (out/n).read_text(encoding='utf-8').splitlines(keepends=True),fromfile='measured/'+n,tofile=out.name+'/'+n)) for n in changed)
    manifest.update(status='PREPARED_UNTESTED_NOT_ADOPTED',source_root=str(out),
                    parent_candidate=str(parent),parent_manifest_sha256=hashlib.sha256((parent/'candidate.json').read_bytes()).hexdigest(),
                    source_sha256=source,changed_files=changed,description=description,
                    tests_started=False,source_review='Source preparation only; no compiler, lint, simulation, synthesis, STA, or formal checks',
                    preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'review.patch').write_text(patch,encoding='utf-8')
    print(json.dumps({'candidate':str(out),'status':manifest['status'],'changed_files':changed},ensure_ascii=False))
    return out


def registered_capacity(t):
    t = change(t, 'wire [BE_WIDTH-1:0] dec_valid = trace_valid_i;',
               'wire [BE_WIDTH-1:0] dec_valid = trace_valid_i & trace_ready_o;')
    t = change(t, '    reg [BE_WIDTH-1:0] trace_ready_r;', '''    reg [BE_WIDTH-1:0] trace_ready_r;
    localparam integer CREDIT_WIDTH=(BE_WIDTH<=1)?1:$clog2(BE_WIDTH+1);
    reg [CREDIT_WIDTH-1:0] rob_credit, rs_credit, lsq_credit, phys_credit;
    reg [CREDIT_WIDTH-1:0] used_rob_credit, used_rs_credit, used_lsq_credit, used_phys_credit;
    integer credit_lane;
    function [CREDIT_WIDTH-1:0] bounded_credit;
        input [15:0] available;
        input [CREDIT_WIDTH-1:0] consumed;
        reg [15:0] remaining;
        begin
            remaining=(available>=consumed)?available-consumed:16'b0;
            bounded_credit=(remaining>=BE_WIDTH)?BE_WIDTH:remaining;
        end
    endfunction
    // At the next edge actual free slots F' = F - accepted + releases.
    // Advertise min(BE_WIDTH,F-accepted), omitting this edge's releases.
    // Thus registered credits never promise more than actual capacity.
    always @* begin
        used_rob_credit=0; used_rs_credit=0; used_lsq_credit=0; used_phys_credit=0;
        for(credit_lane=0;credit_lane<BE_WIDTH;credit_lane=credit_lane+1) begin
            if(dispatch_valid[credit_lane]) begin
                used_rob_credit=used_rob_credit+1'b1;
                used_rs_credit=used_rs_credit+1'b1;
                if(trace_is_load_i[credit_lane] || trace_is_store_i[credit_lane])
                    used_lsq_credit=used_lsq_credit+1'b1;
                if(rename_rd_we[credit_lane]) used_phys_credit=used_phys_credit+1'b1;
            end
        end
    end
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            rob_credit<=0;rs_credit<=0;lsq_credit<=0;phys_credit<=0;
        end else begin
            rob_credit<=bounded_credit(rob_free_count,used_rob_credit);
            rs_credit<=bounded_credit(rs_free_count,used_rs_credit);
            lsq_credit<=bounded_credit(lsq_free_count,used_lsq_credit);
            phys_credit<=bounded_credit({{(16-FREE_COUNT_WIDTH){1'b0}},free_count},used_phys_credit);
        end
    end''')
    start=t.index('    // Ready is a contiguous, resource-qualified prefix')
    end=t.index('    assign trace_ready_o',start)
    part=t[start:end].replace('<= rob_free_count','<= rob_credit').replace('<= rs_free_count','<= rs_credit').replace('<= lsq_free_count','<= lsq_credit').replace('<= free_count','<= phys_credit')
    t=t[:start]+part+t[end:]
    t=change(t, '.rob_free_count_i(rob_free_count), .rs_free_count_i(rs_free_count), .lsq_free_count_i(lsq_free_count),',
             '''.rob_free_count_i({{(16-CREDIT_WIDTH){1'b0}},rob_credit}),
        .rs_free_count_i({{(16-CREDIT_WIDTH){1'b0}},rs_credit}),
        .lsq_free_count_i({{(16-CREDIT_WIDTH){1'b0}},lsq_credit}),''')
    # Keep parameter values unchanged; preserve original banked-read selection.
    t=change(t,'            assign rob_head_views = {6{rob_head_source}};',
             '''            rv32_frequency_control_tree #(.WIDTH(ROB_SLOT_WIDTH),.LEAVES(6)) tree (
                .signal_i(rob_head_source),.views_o(rob_head_views));''')
    return t


def buffered_rob_head(t):
    return change(t,'            assign head_views = {5{head_reg}};',
                  '''            rv32_frequency_control_tree #(.WIDTH(SLOT_WIDTH),.LEAVES(5)) tree (
                .signal_i(head_reg),.views_o(head_views));''')


def bounded_lsq_pointer(t):
    return change(t,'''            p = start;
            for (n = 0; n < LSQ_ENTRIES; n = n + 1) begin
                if (n < amount) begin
                    if (p == LSQ_ENTRIES - 1) p = 0; else p = p + 1;
                end
            end
            advance_slot = p[SLOT_WIDTH-1:0];''', '''            // Depth is a power of two; the original loop clamps amount
            // to [0,depth]. A full traversal returns to the same slot.
            if(LSQ_ENTRIES==1)
                advance_slot=(amount>0)?{SLOT_WIDTH{1'b0}}:start;
            else if(amount<=0 || amount>=LSQ_ENTRIES)
                advance_slot=start;
            else
                advance_slot=start+amount;''')


def divided_arithmetic_stages(t):
    t=change(t,'    reg busy_reg, result_valid_reg;',
             '    reg busy_reg, result_valid_reg;\n    reg prepare_reg, finish_reg;')
    a=t.index('    function [5:0] count_leading_zeros;')
    b=t.index('    wire req_want_remainder',a)
    t=t[:a]+'''    // Hierarchical 16/8/4/2/1 priority selection, rather than a 32-bit
    // serial found-one chain. Zero has an explicit 32 result.
    function [5:0] count_leading_zeros;
        input [31:0] value;
        reg [31:0] shifted;
        reg [5:0] count;
        begin
            shifted=value; count=0;
            if(shifted[31:16]==0) begin count=count+16;shifted=shifted<<16;end
            if(shifted[31:24]==0) begin count=count+8;shifted=shifted<<8;end
            if(shifted[31:28]==0) begin count=count+4;shifted=shifted<<4;end
            if(shifted[31:30]==0) begin count=count+2;shifted=shifted<<2;end
            if(!shifted[31]) count=count+1;
            count_leading_zeros=(value==0)?6'd32:count;
        end
    endfunction

'''+t[b:]
    t=change(t,'''    wire req_dividend_smaller = !req_divide_zero &&
                                !req_signed_overflow &&
                                (req_abs_a < req_abs_b);
''','')
    t=change(t,'''    wire req_fast_result = req_divide_zero || req_signed_overflow ||
                           req_dividend_smaller || req_cache_hit;''', '''    wire req_fast_result = req_divide_zero || req_signed_overflow || req_cache_hit;''')
    t=change(t,'''         (req_dividend_smaller ?
          (req_want_remainder ? req_src1_i : 32'b0) :
          (req_want_remainder ? req_cached_remainder : req_cached_quotient)));
    wire [5:0] req_skip_steps = count_leading_zeros(req_abs_a);''', '''         (req_want_remainder ? req_cached_remainder : req_cached_quotient));
    wire [5:0] prepare_skip_steps = count_leading_zeros(dividend_reg);
    wire [33:0] first_subtract={1'b0,remainder_shift}-{2'b0,divisor_reg};
    wire [33:0] second_subtract={1'b0,remainder_shift_second}-{2'b0,divisor_reg};''')
    t=change(t,'''        if (remainder_shift >= {1'b0, divisor_reg}) begin
            remainder_after = remainder_shift - {1'b0, divisor_reg};''', '''        // The extended subtraction supplies both borrow and remainder.
        if (!first_subtract[33]) begin
            remainder_after = first_subtract[32:0];''')
    t=change(t,'''        if (remainder_shift_second >= {1'b0, divisor_reg}) begin
            remainder_after_second = remainder_shift_second -
                                     {1'b0, divisor_reg};''', '''        if (!second_subtract[33]) begin
            remainder_after_second = second_subtract[32:0];''')
    t=change(t,'quotient_final = ~selected_quotient_after + 32\'d1;',
             'quotient_final = ~quotient_reg + 32\'d1;')
    t=change(t,'quotient_final = selected_quotient_after;', 'quotient_final = quotient_reg;')
    t=change(t,'remainder_final = ~selected_remainder_after[31:0] + 32\'d1;',
             'remainder_final = ~remainder_reg[31:0] + 32\'d1;')
    t=change(t,'remainder_final = selected_remainder_after[31:0];',
             'remainder_final = remainder_reg[31:0];')
    t=change(t,"            busy_reg <= 1'b0;\n            result_valid_reg <= 1'b0;", "            busy_reg <= 1'b0;\n            prepare_reg<=1'b0; finish_reg<=1'b0;\n            result_valid_reg <= 1'b0;")
    t=change(t,'                    step_reg <= req_skip_steps;',
             '''                    prepare_reg<=!req_fast_result;
                    finish_reg<=1'b0;
                    step_reg <= 0;''')
    t=change(t,'                    dividend_reg <= req_abs_a << req_skip_steps;',
             '                    dividend_reg <= req_abs_a;')
    start=t.index('            end else begin\n                dividend_reg <= (step_reg == 31)')
    finish=t.index('                    if (divide_zero_reg) begin',start)
    after=t.index('                end else begin\n                    step_reg <= step_reg + 2\'d2;',finish)
    final_payload=t[finish:after]
    t=t[:start]+'''            end else if(prepare_reg) begin
                // Magnitude arithmetic ended at request capture. CLZ and
                // normalization now begin from registered magnitudes.
                prepare_reg<=1'b0;
                if(dividend_reg<divisor_reg) begin
                    busy_reg<=1'b0;result_valid_reg<=1'b1;
                    result_value_reg<=want_remainder_reg?original_a_reg:32'b0;
                end else begin
                    dividend_reg<=dividend_reg<<prepare_skip_steps;
                    step_reg<=prepare_skip_steps;
                end
            end else if(finish_reg) begin
                // Iteration ended at quotient/remainder registers. Signed
                // correction and the result/cache write occupy this stage.
                finish_reg<=1'b0;busy_reg<=1'b0;result_valid_reg<=1'b1;
'''+final_payload+'''            end else begin
                dividend_reg <= (step_reg == 31) ?
                                {dividend_reg[30:0],1'b0} : {dividend_reg[29:0],2'b0};
                remainder_reg<=selected_remainder_after;
                quotient_reg<=selected_quotient_after;
                if(step_reg>=30) begin
                    finish_reg<=1'b1;
                end else begin
                    step_reg<=step_reg+2'd2;
                end
            end
'''+t[after+len('                end else begin\n                    step_reg <= step_reg + 2\'d2;\n                end\n            end\n'):]
    t=t.replace('// Radix-4 restoring divider.  Two quotient bits are generated per cycle, so',
                '// Two restoring digit steps per cycle with separate normalization and final correction, so')
    return t


def parallel_completion(t):
    # Reuse our earlier source-only rank draft, replacing distance arithmetic
    # with a static circular-order relation and adding balanced payload trees.
    from prepare_completion_rank_arbiter import ARBITER
    arb=ARBITER
    arb=change(arb,'    wire [SOURCE_WIDTH-1:0] source_distance [0:SOURCES-1];',
               '    wire [SOURCES-1:0] source_above_cursor;')
    arb=change(arb,'''            localparam [SOURCE_WIDTH:0] NUMBER=rank_source;
            localparam [SOURCE_WIDTH:0] SOURCE_COUNT=SOURCES;
            wire [SOURCE_WIDTH:0] distance_full=NUMBER+
                ((direct_rr_reg>NUMBER)?SOURCE_COUNT:0)-direct_rr_reg;
            assign source_distance[rank_source]=distance_full[0 +: SOURCE_WIDTH];''',
               '''            // Above-cursor sources precede wrapped sources; within
            // either part of the circle static source number determines order.
            assign source_above_cursor[rank_source]=(rank_source>=direct_rr_reg);''')
    arb=change(arb,'source_distance[rank_other]<source_distance[rank_source];',
               '''((source_above_cursor[rank_other]==source_above_cursor[rank_source]) ?
                         (rank_other<rank_source) : source_above_cursor[rank_other]);''')
    t=change(t,'    reg [SOURCES-1:0] direct_eligible, direct_used;',
             '    wire [SOURCES-1:0] direct_eligible, direct_used;')
    start=t.index('    // Reserve ALL held lanes before filling any unheld lane.')
    stop=t.index('    always @(posedge clk_i) begin',start)
    payload='''
    localparam integer DIRECT_META_WIDTH=TAG_WIDTH+PHYS_ADDR_WIDTH+7;
    wire [DIRECT_META_WIDTH-1:0] direct_meta [0:CDB_WIDTH-1];
    wire [31:0] direct_value [0:CDB_WIDTH-1],direct_target [0:CDB_WIDTH-1];
    wire [63:0] direct_memory [0:CDB_WIDTH-1];
    genvar payload_lane,payload_source,payload_node;
    generate for(payload_lane=0;payload_lane<CDB_WIDTH;payload_lane=payload_lane+1) begin:g_direct_payload
        wire [DIRECT_META_WIDTH-1:0] meta_tree [1:2*RANK_LEAVES-1];
        wire [31:0] value_tree [1:2*RANK_LEAVES-1],target_tree [1:2*RANK_LEAVES-1];
        wire [63:0] memory_tree [1:2*RANK_LEAVES-1];
        for(payload_source=0;payload_source<RANK_LEAVES;payload_source=payload_source+1) begin:g_source
            if(payload_source<SOURCES) begin:g_live
                wire [3:0] selected_views;
                rv32_frequency_control_tree #(.LEAVES(4)) select_tree (
                    .signal_i(selected_mask[payload_lane][payload_source] && !reset_i && !flush_i),
                    .views_o(selected_views));
                assign meta_tree[RANK_LEAVES+payload_source]={DIRECT_META_WIDTH{selected_views[0]}} &
                    {producer_tag_i[payload_source*TAG_WIDTH +: TAG_WIDTH],
                     producer_phys_rd_i[payload_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                     producer_rd_we_i[payload_source] && !producer_is_store_i[payload_source],
                     producer_is_store_i[payload_source],producer_is_branch_i[payload_source],
                     producer_branch_taken_i[payload_source],producer_redirect_valid_i[payload_source],
                     producer_is_memory_i[payload_source],producer_is_load_i[payload_source]};
                assign value_tree[RANK_LEAVES+payload_source]={32{selected_views[1]}} &
                    producer_value_i[payload_source*32 +: 32];
                assign memory_tree[RANK_LEAVES+payload_source]={64{selected_views[2]}} &
                    {producer_addr_i[payload_source*32 +: 32],producer_store_data_i[payload_source*32 +: 32]};
                assign target_tree[RANK_LEAVES+payload_source]={32{selected_views[3]}} &
                    producer_branch_target_i[payload_source*32 +: 32];
            end else begin:g_zero
                assign meta_tree[RANK_LEAVES+payload_source]=0;
                assign value_tree[RANK_LEAVES+payload_source]=0;
                assign memory_tree[RANK_LEAVES+payload_source]=0;
                assign target_tree[RANK_LEAVES+payload_source]=0;
            end
        end
        for(payload_node=1;payload_node<RANK_LEAVES;payload_node=payload_node+1) begin:g_or
            assign meta_tree[payload_node]=meta_tree[2*payload_node]|meta_tree[2*payload_node+1];
            assign value_tree[payload_node]=value_tree[2*payload_node]|value_tree[2*payload_node+1];
            assign memory_tree[payload_node]=memory_tree[2*payload_node]|memory_tree[2*payload_node+1];
            assign target_tree[payload_node]=target_tree[2*payload_node]|target_tree[2*payload_node+1];
        end
        assign direct_meta[payload_lane]=meta_tree[1];
        assign direct_value[payload_lane]=value_tree[1];
        assign direct_memory[payload_lane]=memory_tree[1];
        assign direct_target[payload_lane]=target_tree[1];
    end endgenerate

'''
    t=t[:start]+arb+payload+t[stop:]
    t=change(t,'''                        producer_tag_i[direct_selected_source[direct_state_lane]*TAG_WIDTH +: TAG_WIDTH];''',
             '''                        direct_meta[direct_state_lane][PHYS_ADDR_WIDTH+7 +: TAG_WIDTH];''')
    start=t.index('            for (lane = 0; lane < CDB_WIDTH; lane = lane + 1) begin',t.index('        if (BYPASS == 2) begin'))
    stop=t.index('        end\n    end\n\n    assign prf_write_valid_o',start)
    t=t[:start]+'''            for(lane=0;lane<CDB_WIDTH;lane=lane+1) begin
                cdb_valid_o[lane]=!reset_i && !flush_i && direct_selected_valid[lane];
                {cdb_tag_o[lane*TAG_WIDTH +: TAG_WIDTH],
                 cdb_phys_rd_o[lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                 cdb_rd_we_o[lane],cdb_is_store_o[lane],cdb_is_branch_o[lane],
                 cdb_branch_taken_o[lane],cdb_redirect_valid_o[lane],
                 cdb_is_memory_o[lane],cdb_is_load_o[lane]}=direct_meta[lane];
                cdb_value_o[lane*32 +: 32]=direct_value[lane];
                {cdb_addr_o[lane*32 +: 32],cdb_store_data_o[lane*32 +: 32]}=direct_memory[lane];
                cdb_branch_target_o[lane*32 +: 32]=direct_target[lane];
                for(source=0;source<SOURCES;source=source+1)
                    if(!reset_i && !flush_i && selected_mask[lane][source])
                        producer_ready_o[source]=cdb_ready_i[lane];
            end
'''+t[stop:]
    return t


def buffered_issue_queue(t):
    start=t.index('// A selected instruction is removed from the RS only when this slot accepts it.')
    return t[:start]+'''// Two retained entries break the functional-unit ready -> RS ready path.
// Unstalled first-result latency is still one registered selection stage.
module rv32_issue_pipeline_slot #(
    parameter integer PAYLOAD_WIDTH=192, TAG_WIDTH=17, ROB_ENTRIES=64,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES)
) (
    input wire clk_i, reset_i, flush_i, recovery_i,
    input wire [SW-1:0] head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire valid_i, eligible_i,
    output wire ready_o,
    input wire [PAYLOAD_WIDTH-1:0] data_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire valid_o,
    input wire ready_i,
    output wire [PAYLOAD_WIDTH-1:0] data_o
);
    localparam integer CHUNKS=(PAYLOAD_WIDTH+31)/32;
    reg [1:0] count,entry_valid;
    reg read_slot,write_slot;
    reg [PAYLOAD_WIDTH-1:0] payload [0:1];
    reg [TAG_WIDTH-1:0] saved_tag [0:1];
    wire [1:0] recovery_keep;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-head_i;
    wire push=valid_i && ready_o;
    wire pop=valid_o && ready_i;
    wire [CHUNKS-1:0] read_views;
    rv32_frequency_control_tree #(.LEAVES(CHUNKS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    // Ready depends only on registered occupancy, with one spare entry to
    // absorb backpressure. A full queue advertises space after its pop edge.
    assign ready_o=(count<2) && eligible_i && !reset_i && !flush_i && !recovery_i;
    assign valid_o=(count!=0) && !reset_i && !flush_i && !recovery_i;
    genvar queue_row,chunk;
    generate for(queue_row=0;queue_row<2;queue_row=queue_row+1) begin:g_row
        wire [SW-1:0] age=saved_tag[queue_row][3 +: SW]-head_i;
        assign recovery_keep[queue_row]=entry_valid[queue_row] &&
            saved_tag[queue_row][0] && age<branch_age;
        wire [CHUNKS:0] write_views;
        rv32_frequency_control_tree #(.LEAVES(CHUNKS+1)) write_tree (
            .signal_i(push && write_slot==queue_row),.views_o(write_views));
        always @(posedge clk_i) if(write_views[CHUNKS]) saved_tag[queue_row]<=tag_i;
        for(chunk=0;chunk<CHUNKS;chunk=chunk+1) begin:g_chunk
            localparam integer LOW=chunk*32;
            localparam integer BITS=(PAYLOAD_WIDTH-LOW>=32)?32:PAYLOAD_WIDTH-LOW;
            always @(posedge clk_i) if(write_views[chunk])
                payload[queue_row][LOW +: BITS]<=data_i[LOW +: BITS];
        end
    end
    for(chunk=0;chunk<CHUNKS;chunk=chunk+1) begin:g_read
        localparam integer LOW=chunk*32;
        localparam integer BITS=(PAYLOAD_WIDTH-LOW>=32)?32:PAYLOAD_WIDTH-LOW;
        assign data_o[LOW +: BITS]=read_views[chunk]?
            payload[1][LOW +: BITS]:payload[0][LOW +: BITS];
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            count<=0;entry_valid<=0;read_slot<=0;write_slot<=0;
        end else if(recovery_i) begin
            entry_valid<=recovery_keep;
            case(recovery_keep)
                2'b11: count<=2;
                2'b01: begin count<=1;read_slot<=0;write_slot<=1;end
                2'b10: begin count<=1;read_slot<=1;write_slot<=0;end
                default: begin count<=0;read_slot<=0;write_slot<=0;end
            endcase
        end else begin
            count<=count+push-pop;
            if(pop) begin entry_valid[read_slot]<=1'b0;read_slot<=!read_slot;end
            if(push) begin entry_valid[write_slot]<=1'b1;write_slot<=!write_slot;end
        end
    end
endmodule
'''


def cached_rs_age_order(t):
    t=change(t,'    parameter integer ALLOC_STATIC_WRITE = 0,',
             '    parameter integer ALLOC_STATIC_WRITE = 0,\n    parameter integer AGE_ORDER_MATRIX = 0,')
    t=change(t,'    wire [COUNT_WIDTH-1:0] ready_rank [0:ENTRIES-1];',
             '    wire [COUNT_WIDTH-1:0] ready_rank [0:ENTRIES-1];\n    wire [ENTRIES-1:0] cached_age_precedes [0:ENTRIES-1];')
    t=change(t,'''wire older = (age_mem[rank_other] < age_mem[rank_slot]) ||
                        ((rank_other < rank_slot) && (age_mem[rank_other] == age_mem[rank_slot]));''',
             '''wire older = ((AGE_ORDER_MATRIX != 0) && (ALLOC_STATIC_WRITE != 0)) ?
                        cached_age_precedes[rank_other][rank_slot] :
                        ((age_mem[rank_other] < age_mem[rank_slot]) ||
                         ((rank_other < rank_slot) && (age_mem[rank_other] == age_mem[rank_slot])));''')
    t=change(t,'    wire [ENTRIES-1:0] alloc_row_write;',
             '    wire [ENTRIES-1:0] alloc_row_write;\n    wire [BE_WIDTH-1:0] alloc_row_grants [0:ENTRIES-1];')
    t=change(t,'            assign alloc_row_write[ar] = |allocation_match_bits;',
             '            assign alloc_row_grants[ar] = grants;\n            assign alloc_row_write[ar] = |allocation_match_bits;')
    # Existing source-only draft stores EXACT unsigned comparisons, including
    # wrap and slot tie breaking. It is not a new scheduling/age policy.
    draft=Path(__file__).with_name('prepare_rs_age_matrix_candidate.py').read_text(encoding='utf-8')
    insert=draft.split("    insert = '''",1)[1].split("'''",1)[0]
    return change(t,'    // Allocate a contiguous prefix and choose the oldest ready entries for',
                  insert+'    // Allocate a contiguous prefix and choose the oldest ready entries for')


def enable_cached_rs_age(t):
    return change(t,'.ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE),',
                  '.AGE_ORDER_MATRIX(1), .ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE),')


if __name__=='__main__':
    d=prepare('D_staged_recovery',ROOT/'C_split_signed_multiplier',
            {'rtl/backend/rv32_rob.v':staged_rob,'rtl/backend/rv32_backend_joint.v':staged_backend},
            'C plus immediate preview redirect, registered selective recovery/RAT/reclaim, pending-based allocation and execution freeze')
    e=prepare('E_registered_capacity_and_arithmetic',d,
            {'rtl/backend/rv32_backend_joint.v':registered_capacity,
             'rtl/backend/rv32_rob.v':buffered_rob_head,
             'rtl/backend/rv32_lsq.v':bounded_lsq_pointer,
             'rtl/rv32m_divider.v':divided_arithmetic_stages},
            'D plus conservative registered allocation credits, local buffered ROB head domains, bounded LSQ pointer arithmetic, separated divider normalization/final correction and borrow-based restoring steps')
    f=prepare('F_parallel_completion',e,
            {'rtl/backend/rv32_completion_network.v':parallel_completion},
            'E plus parallel circular source ordering, held-source reservation, balanced one-hot payload reduction and local selection buffers')
    g=prepare('G_buffered_issue',f,
            {'rtl/backend/rv32_backend_joint.v':buffered_issue_queue},
            'F plus two-entry tagged issue queues with occupancy-only input ready and selective recovery')
    prepare('H_cached_issue_age',g,
            {'rtl/backend/rv32_reservation_station.v':cached_rs_age_order,
             'rtl/backend/rv32_backend_joint.v':enable_cached_rs_age},
            'G plus allocation-time cached exact unsigned numeric age comparisons')
