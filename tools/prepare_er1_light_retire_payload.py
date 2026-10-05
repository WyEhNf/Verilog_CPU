"""Remove unused optional ROB trace payload in an ER1-derived source candidate."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import ROOT, read, sha, write
from review_frequency_dx_sources import blocks

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A3_early_load_hit_bypass_r32_p56_rs8_d512'
TARGET=BASE/'A4R2_light_retire_payload'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def owned_field(field,width):
    return f'''        rv32_rob_owned_field #(.WIDTH({width})) {field}_mem_owner (
            .clk_i(clk_i),.write_i({field}_mem_write_enable[storage_row]),
            .data_i({field}_mem_write_data[storage_row]),.data_o({field}_mem[storage_row]));'''


def main():
    assert not TARGET.exists()
    pm=read(PARENT/'candidate.json')
    for name,h in pm['source_sha256'].items():
        assert sha(PARENT/name)==h
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    changes=[]
    for name in ('rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v'):
        dest=TARGET/name;text=dest.read_text(encoding='utf-8')
        enabled='1' if name.endswith('student_top.v') else '0'
        text=once(text,'parameter integer ROB_MMIO_PREDECODE = ',
                  'parameter integer LIGHT_RETIRE_PAYLOAD = '+enabled+',\n    parameter integer ROB_MMIO_PREDECODE = ')
        anchor='.MMIO_PREDECODE(ROB_MMIO_PREDECODE)' if name.endswith('rv32_backend_joint.v') else '.ROB_MMIO_PREDECODE(ROB_MMIO_PREDECODE)'
        text=once(text,anchor,anchor+', .LIGHT_RETIRE_PAYLOAD(LIGHT_RETIRE_PAYLOAD)')
        dest.write_text(text,encoding='utf-8');changes.append(name)
    name='rtl/backend/rv32_rob.v';dest=TARGET/name
    old=dest.read_text(encoding='utf-8');text=old
    text=once(text,'parameter integer MMIO_PREDECODE = 0,',
              '''parameter integer MMIO_PREDECODE = 0,
    // Enable only when commit PC/instruction and store payload outputs are
    // unconnected. Authority, error, terminal data and full tags stay intact.
    // MMIO_PREDECODE=0 retains address/mask storage for terminal detection.
    parameter integer LIGHT_RETIRE_PAYLOAD = 0,''')
    for field,width in (('pc','31+1'),('inst','31+1'),('store_addr','31+1'),('store_mask','3+1')):
        body=owned_field(field,width)
        guard='LIGHT_RETIRE_PAYLOAD==0' if field in ('pc','inst') else '(LIGHT_RETIRE_PAYLOAD==0) || (MMIO_PREDECODE==0)'
        bits='32' if field!='store_mask' else '4'
        replacement=f'''        if({guard}) begin:g_full_{field}
{body}
        end else begin:g_unobserved_{field}
            assign {field}_mem[storage_row]={bits}'b0;
        end'''
        text=once(text,body,replacement)
    # The trace PC/instruction never enter the kept bank allocation payload
    # in the light mode. Other fields keep identical ordering/widths.
    text=once(text,'alloc_pc_i[alloc_source*32 +: 32],alloc_inst_i[alloc_source*32 +: 32],',
              '''((LIGHT_RETIRE_PAYLOAD==0)?alloc_pc_i[alloc_source*32 +: 32]:32'b0),
                            ((LIGHT_RETIRE_PAYLOAD==0)?alloc_inst_i[alloc_source*32 +: 32]:32'b0),''')
    dest.write_text(text,encoding='utf-8');changes.append(name)
    clock_count=0
    for name in pm['source_sha256']:
        if name.endswith('.v'):
            before=blocks((PARENT/name).read_text(encoding='utf-8'))
            after=blocks((TARGET/name).read_text(encoding='utf-8'))
            assert before==after,name
            clock_count+=len(after)
    record=dict(pm)
    record.update(status='PREPARED_UNTESTED_NOT_ADOPTED',source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
                  parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
                  changed_from_parent_files=changes,source_sha256={n:sha(TARGET/n) for n in pm['source_sha256']})
    record['parameter_overrides']=dict(pm['parameter_overrides'],LIGHT_RETIRE_PAYLOAD=1)
    record['implemented_groups']=list(pm['implemented_groups'])+[dict(name='Drop unused ROB trace and duplicate store address/mask payload',
        original_authority_and_terminal_data_kept=True,enabled_optional_mode='LIGHT_RETIRE_PAYLOAD=1',
        removed_declared_payload_bits=32*(32+32+32+4),new_declared_state_bits=0)]
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_REVIEW_ONLY_NOT_FULL_CORE_PROOF',candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
               parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_files=changes,
               compound_clocked_blocks_text_equal=clock_count,new_declared_state_bits=0,
               removed_declared_payload_bits_current_profile=3200,
               no_effect_on_valid_ready_generation_error_mmio_storage=True,
               full_default_mode_field_owners_retained=True,full_default_mode_widths_and_assignments_retained=True,
               source_projection=[
                   'cpu_core only declares/connects commit_pc,commit_inst,commit_store_addr,commit_store_mask,commit_store_data; these are absent from student_top output ports.',
                   'backend LSQ store admission consumes only rob_store_commit_valid/ready/tag. Store address/data/mask for AXI remain in LSQ.',
                   'ROB pc_mem and inst_mem are used only in commit read/output payloads, not recovery/rename/ready/terminal predicates.',
                   'With MMIO_PREDECODE=1, head_mmio_word comes from mmio_word_mem, qualified by the same completion events. Store address/mask are then used only to form ignored store payload outputs.',
                   'value_mem and store_data_mem remain: HALT return uses head_value, MMIO return uses head_store_data. Error, store_wait/store_sent, valid/ready, generation and register mappings remain.',
                   'MMIO_PREDECODE=0 retains real store address/mask regardless of light mode. Default LIGHT_RETIRE_PAYLOAD=0 retains all original field owners.',
                   'All 69 compound clocked blocks are text-identical. This is source projection evidence; final whole-core correctness remains necessary.'
               ],tests_started=False,adopted=False,candidate_area_um2=None,candidate_ipc=None,candidate_fmax_mhz=None)
    write(BASE/'A4_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','compound_clocked_blocks_text_equal','removed_declared_payload_bits_current_profile','tests_started')})


if __name__=='__main__':main()
