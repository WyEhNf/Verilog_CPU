"""Remove a redundant branch-map override under the backend undo contract."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A65_direct_recovery_apply'
TARGET = BASE / 'A66_rat_suffix_branch_mapping'
REVIEW = BASE / 'A66_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_rat_recovery.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer IMPL = 1,',
        '''    parameter integer IMPL = 1,
    // Caller guarantees rat_i is the current speculative map and old_phys_i
    // records every accepted rename in program order. Suffix undo already
    // keeps the branch's own destination under this contract.
    parameter integer SUFFIX_KEEPS_BRANCH_MAPPING = 0,''')
    old_output = '''    generate for (arch = 0; arch < 32; arch = arch + 1) begin : g_keep_branch
        assign restore_o[arch*PAW +: PAW] = (arch != 0 && branch_rd_we_i && branch_rd_i == arch) ?
            branch_new_phys_i : undo_result[arch*PAW +: PAW];
    end endgenerate'''
    new_output = '''    generate if(SUFFIX_KEEPS_BRANCH_MAPPING!=0) begin:g_suffix_keeps_branch
        // The oldest killed writer's old map is the retained prefix map.
        // With no killed writer, the current RAT already is that same map.
        assign restore_o=undo_result;
    end else begin:g_explicit_branch_mapping
        for (arch = 0; arch < 32; arch = arch + 1) begin : g_keep_branch
            assign restore_o[arch*PAW +: PAW] = (arch != 0 && branch_rd_we_i && branch_rd_i == arch) ?
                branch_new_phys_i : undo_result[arch*PAW +: PAW];
        end
    end endgenerate'''
    text = once(text, old_output, new_output)
    # The entire age/match/oldest-writer calculation remains byte-exact.
    begin = '    wire [32*PAW-1:0] undo_result;'
    assert text[text.index(begin):text.index('    generate if(SUFFIX_KEEPS_BRANCH_MAPPING')]==original[original.index(begin):original.index(old_output)]
    changes[name] = text
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RAT_RECOVERY_IMPL = 0,',
        '    parameter integer RAT_RECOVERY_IMPL = 0,\n    parameter integer RAT_SUFFIX_BRANCH_MAPPING = 0,')
    text = once(text,
        'rv32_rat_recovery #(.ROB_ENTRIES(ROB_ENTRIES), .PAW(PAW), .IMPL(2)) rat_recovery (',
        '''rv32_rat_recovery #(.ROB_ENTRIES(ROB_ENTRIES), .PAW(PAW), .IMPL(2),
            .SUFFIX_KEEPS_BRANCH_MAPPING(RAT_SUFFIX_BRANCH_MAPPING)) rat_recovery (''')
    # This instantiation exists only in nonzero checkpoint/parallel RAT modes.
    assert 'generate if (RAT_RECOVERY_IMPL != 0 && CHECKPOINT_IMPL != 0)' in text
    changes[name] = text
    for name, default in [('rtl/cpu_core.v',0),('rtl/course/student_top.v',1)]:
        text = (PARENT/name).read_text(encoding='utf-8')
        text = once(text, f'    parameter integer RAT_RECOVERY_IMPL = {default},',
            f'    parameter integer RAT_RECOVERY_IMPL = {default},\n    parameter integer RAT_SUFFIX_BRANCH_MAPPING = {default},')
        text = once(text, '.RAT_RECOVERY_IMPL(RAT_RECOVERY_IMPL),',
            '.RAT_RECOVERY_IMPL(RAT_RECOVERY_IMPL), .RAT_SUFFIX_BRANCH_MAPPING(RAT_SUFFIX_BRANCH_MAPPING),')
        changes[name] = text
    # Bind the source contract used by the manual argument. This checks source
    # identity/structure only; it does not execute or verify RTL behavior.
    rename = (PARENT/'rtl/rv32_rename_unit.v').read_text(encoding='utf-8')
    backend = (PARENT/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    for marker in [
        'rename_old_phys_o[lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH] = rat[decoded_rd_i[lane*5 +: 5]];',
        'rename_new_phys_o[bypass_lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];',
        'bundle_rat[decoded_rd_i[(lane*5) +: 5]] =',
        '.signal_i(rename_valid_o & rename_rd_we_o),.views_o(map_valid_views)',
    ]:
        assert marker in rename, marker
    for marker in [
        'wire [BE_WIDTH-1:0] dispatch_valid = rename_valid;',
        'assign rob_alloc_valid = dispatch_valid;',
        '.alloc_rd_we_i(rename_rd_we)',
        '.alloc_old_phys_i(rob_alloc_old_phys)',
        '.alloc_new_phys_i(rob_alloc_new_phys)',
        'rob_alloc_old_phys = rename_old_phys;',
        'rob_alloc_new_phys = rename_new_phys;',
    ]:
        assert marker in backend, marker
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name, text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_RAT_SUFFIX_BRANCH_MAPPING_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],RAT_SUFFIX_BRANCH_MAPPING=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],rat_suffix_keeps_branch_mapping=True,
        rat_extra_branch_destination_override_removed=True,new_ff_bits_for_rat_override=0,new_sram_bits_for_rat_override=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Under the backend current-speculative-RAT and program-order old-physical-chain contract, suffix undo already preserves every retained mapping including the branch destination. Bypass the additional branch-rd/phys override mux in nonzero checkpoint/parallel recovery mode. All age/match/oldest-writer logic and full ROB lifetime qualification remain unchanged; standalone/default interface preserves explicit override.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        rat_suffix_branch_mapping_source_argument=True,rat_override_path_removed='ROB selected branch destination -> rd compare -> final per-register restore mux',
        rat_override_area_frequency_gain_unknown=True)
    write(TARGET/'candidate.json',record)
    proof = dict(status='SOURCE_RAT_SUFFIX_BRANCH_MAPPING_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,adopted=False,
        new_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        atomic_rename_contract_sources_sha256={name:sha(TARGET/name) for name in ['rtl/rv32_rename_unit.v','rtl/backend/rv32_backend_joint.v','rtl/backend/rv32_rob.v']},
        source_arguments=[
            'For architectural register a, let P be its speculative mapping just after the retained branch prefix. Each younger accepted write records the preceding map in old_phys and installs new_phys; same-bundle repeated destinations record the youngest accepted earlier lane. ROB accepts the same rename_valid prefix and stores these same old/new maps. Current RAT is the end of that chain.',
            'If no killed suffix writer targets a, current RAT(a)=P(a), so undo passes P through. Otherwise, the oldest killed writer records old_phys=P(a), and the unchanged wrap-aware oldest-writer selector returns it. Thus suffix undo returns P for every register. If the branch writes a, P(a) is its new physical destination; an explicit second override returns the same value.',
            'Older commits update RRAT/free ownership but do not rewrite speculative RAT. Surviving older uncompleted instructions keep their map. Apply prevents any new rename/allocation/commit from changing the current prefix while all consumers restore it. Previous selective recovery leaves the same contract inductively; full GEN qualification still belongs to the ROB accepted recovery event.',
            'All age/valid/rd matching and oldest-writer/wrap selection are byte-exact. New parameter defaults0 in standalone/core/backend, preserving explicit branch override for arbitrary input tuples that do not meet the contract. Backend enables it only in the pre-existing nonzero CHECKPOINT_IMPL and RAT_RECOVERY_IMPL generate branch; course top1 uses that contract.',
            'Course no longer consumes branch_rd_we/rd/new_phys for final parallel RAT override. Their other legacy consumers are elaboration-disabled in this profile, so synthesis can prune that selected destination payload path. ROB recovery valid/GEN and occupancy/age authority, branch completion/link-value write, reclaim bitmap and architectural destination ownership are not removed.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. This is a manual invariant argument bound to frozen source, not equivalence or a measured Fmax/area benefit. Future batch must include JAL/JALR rd=x1/x5/nonstandard/zero, several younger writes to the same destination (including same rename bundle), wrap/full ROB, branch link value consumers, older commit on capture, reset/flush and mode0/fallback.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__=='__main__':
    main()
