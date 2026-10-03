"""Prepare final recovery query domains from K; source editing only."""
from prepare_staged_frequency_candidate import change, prepare, ROOT


def local_recovery_queries(t):
    replacements = {
        '.branch_slot_i(branch_pending_tag[3 +: ROB_SLOT_WIDTH])': '.branch_slot_i(recovery_tag_views[TAG_WIDTH+3 +: ROB_SLOT_WIDTH])',
        'recovery_rat_branch_age = branch_pending_tag[3 +: ROB_SLOT_WIDTH]': 'recovery_rat_branch_age = recovery_tag_views[TAG_WIDTH+3 +: ROB_SLOT_WIDTH]',
        'recovery_rs_branch_slot = branch_pending_tag[3 +: ROB_SLOT_WIDTH]': 'recovery_rs_branch_slot = recovery_tag_views[2*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]',
        'recovery_completion_branch_age = branch_pending_tag[3 +: ROB_SLOT_WIDTH]': 'recovery_completion_branch_age = recovery_tag_views[3*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]',
        ".recovery_tag_i({ {(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, branch_pending_tag })": ".recovery_tag_i({ {(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, recovery_tag_views[0 +: TAG_WIDTH] })",
        '.recovery_i(recovery_domains[4]), .recovery_tag_i(branch_pending_tag)': '.recovery_i(recovery_domains[4]), .recovery_tag_i(recovery_tag_views[4*TAG_WIDTH +: TAG_WIDTH])',
        '.recovery_valid_i(recovery_domains[5]), .recovery_tag_i(branch_pending_tag)': '.recovery_valid_i(recovery_domains[5]), .recovery_tag_i(recovery_tag_views[5*TAG_WIDTH +: TAG_WIDTH])',
        'producer_recovery_branch_age = branch_pending_tag[3 +: ROB_SLOT_WIDTH]': 'producer_recovery_branch_age = recovery_tag_views[6*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]',
        'alu_recovery_branch_age = branch_pending_tag[3 +: ROB_SLOT_WIDTH]': 'alu_recovery_branch_age = recovery_tag_views[7*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]',
        "completion_tag_r = {{(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, branch_pending_tag}": "completion_tag_r = {{(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, recovery_tag_views[0 +: TAG_WIDTH]}",
        '(rob_commit_tag[TAG_WIDTH-1:0] == branch_pending_tag)': '(rob_commit_tag[TAG_WIDTH-1:0] == recovery_tag_views[0 +: TAG_WIDTH])',
    }
    for old,new in replacements.items():
        t=change(t,old,new)
    t=change(t,'    reg [TAG_WIDTH-1:0] branch_pending_tag;', '''    reg [TAG_WIDTH-1:0] branch_pending_tag;
    // Registered descriptors still need electrical separation at their
    // consumers. These are priced course-library cells, without new cycles.
    wire [8*TAG_WIDTH-1:0] recovery_tag_views;
    rv32_frequency_control_tree #(.WIDTH(TAG_WIDTH),.LEAVES(8)) recovery_tag_tree (
        .signal_i(branch_pending_tag),.views_o(recovery_tag_views));''')
    return t


if __name__=='__main__':
    prepare('L_local_recovery_queries',ROOT/'K_cache_request_domains',
            {'rtl/backend/rv32_backend_joint.v':local_recovery_queries},
            'K plus eight physically distinct priced recovery tag query domains; unchanged stages and exact recovery rules')
