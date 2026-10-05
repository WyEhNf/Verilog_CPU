"""Prepare ER1-derived early-load and area profiles without tests/adoption."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from manage_frozen_baseline_programs import ROOT, read, sha, write

PARENT=Path('F:/CPU2026Candidates/frequency_research_20261003/ER1_parallel_lsq_pick_slot_identity')
BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')


def replace_once(source, old, new):
    assert source.count(old)==1, old
    return source.replace(old,new)


def prepare(name, profile):
    target=BASE/name
    assert not target.exists()
    original=read(PARENT/'candidate.json')
    for path,expected in original['source_sha256'].items():
        assert sha(PARENT/path)==expected, path
        dest=target/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/path,dest)
    modified=[]
    for path in ('rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v'):
        dest=target/path
        text=dest.read_text(encoding='utf-8')
        text=replace_once(text,'parameter integer EARLY_STORE_ADDRESS = ',
                          'parameter integer EARLY_LOAD_ADDRESS = '+('1' if path.endswith('student_top.v') else '0')+',\n    parameter integer EARLY_STORE_ADDRESS = ')
        if path.endswith('rv32_backend_joint.v'):
            text=replace_once(text,
                'd_valid[io_lane] && d_is_store[io_lane] && rs_src1_ready[io_lane];',
                'd_valid[io_lane] && (d_is_store[io_lane] ||\n                        ((EARLY_LOAD_ADDRESS != 0) && d_is_load[io_lane])) && rs_src1_ready[io_lane];')
            text=replace_once(text,
                '// Only stores with alloc_addr_valid observe this payload.\n                    // Loads leave addr_ready clear until their ordinary AGU update.',
                '// Ready loads may use the same allocation address when enabled.\n                    // Ordinary AGU issue and full-tag LSQ updates remain active.')
        else:
            text=replace_once(text,'.EARLY_STORE_ADDRESS(EARLY_STORE_ADDRESS)',
                              '.EARLY_LOAD_ADDRESS(EARLY_LOAD_ADDRESS), .EARLY_STORE_ADDRESS(EARLY_STORE_ADDRESS)')
        dest.write_text(text,encoding='utf-8')
        modified.append(path)
    # Same exact identifier-only repair as the independent baseline build.
    path='rtl/backend/rv32_lsq.v'
    dest=target/path
    content=dest.read_bytes();lines=content.splitlines(keepends=True)
    changed=0
    for index,line in enumerate(lines):
        if line.lstrip().startswith((b'wire ',b'assign ')) and re.search(rb'\bmatches\b',line):
            lines[index]=re.sub(rb'\bmatches\b',b'response_query_matches',line);changed+=1
    updated=b''.join(lines)
    assert changed==4 and updated.replace(b'response_query_matches',b'matches')==content
    dest.write_bytes(updated);modified.append(path)
    if profile:
        dest=target/'rtl/course/student_top.v'
        text=dest.read_text(encoding='utf-8')
        for key,value in profile.items():
            text,count=re.subn(r'\b'+key+r'\s*=\s*\d+',key+' = '+str(value),text,count=1)
            assert count==1,key
        dest.write_text(text,encoding='utf-8')
    record=dict(original)
    groups=list(original['implemented_groups'])
    groups.append(dict(name='ER1 native identifier compatibility',modified_file='rtl/backend/rv32_lsq.v',
                       architecture_change=False,new_declared_state_bits=0))
    groups.append(dict(name='Early ready-load LSQ allocation',modified_files=modified[:3],
                       reuses_existing_allocation_adders=True,ordinary_AGU_kept=True,
                       LSQ_ordering_and_forwarding_kept=True,new_declared_state_bits=0))
    if profile:
        groups.append(dict(name='Area profile with four-wide issue retained',parameter_changes=profile,
                           occupancy_and_cache_miss_tradeoffs_unmeasured=True))
    record.update(status='PREPARED_UNTESTED_NOT_ADOPTED',source_root=str(target),
                  created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),
                  parent_candidate_sha256=sha(PARENT/'candidate.json'),measured_parent_run='F:/CPU2026CourseRuns/architecture_ER1_20261005',
                  implemented_groups=groups,adopted=False,tests_started=False,
                  parent_frequency_mhz=371.41820819731595, candidate_frequency_mhz=None,candidate_ipc=None,candidate_area_um2=None,
                  target=dict(minimum_fmax_mhz=300,ipc=1.1,total_area_um2=36000),
                  changed_from_parent_files=modified,source_sha256={n:sha(target/n) for n in original['source_sha256']})
    record['parameter_overrides']=dict(original['parameter_overrides'],EARLY_LOAD_ADDRESS=1,**profile)
    write(target/'candidate.json',record)
    return dict(candidate=str(target),candidate_sha256=sha(target/'candidate.json'),parameter_changes=profile,
                new_tests_started=False,adopted=False)


def main():
    candidates=[prepare('A1_early_load_allocation',{}),
                prepare('A2_early_load_r32_p56_rs8_d512',dict(ROB_ENTRIES=32,PHYS_REGS=56,RS_ENTRIES=8,DCACHE_LINES=512))]
    report=ROOT/'reports/ER1_tier3_source_batch_2026-10-05.md'
    assert not report.exists()
    report.write_text('''# ER1 基础上的 IPC/面积源码候选（未测试、未采用）

目标：频率 >300MHz、IPC≥1.1、含SRAM总面积≤36,000μm²。ER1 IPC基线正在独立后台测量。

A1保持ER1资源配置，只让基址已准备好的load复用现有store分配地址加法器，在进入LSQ时即设置地址ready。
这样有机会提前经过原有LSQ排序/老store检查/转发/请求选择，减少等待RS与普通AGU地址回写的周期。
普通AGU路径仍执行；RS、ROB、完整代际tag、load错误、store可见性和LSQ依赖检查全部保留。
这改变load地址可用时间，不是全核等价证明。可能存在调度/重复更新/恢复边界问题，需先做源码生命周期审查。
未增加地址加法器和寄存器。EARLY_LOAD_ADDRESS默认0保留其他实例；候选顶层启用1。

A2在A1基础上保存一个联合面积配置：ROB64→32、PRF64→56、RS12→8、D-cache1024→512行。
取指/后端/整数发射宽度4、CDB3、LSQ16、I-cache128、I/D MSHR8/4保持。
减少队列状态与选择/比较网络，并减少真实SRAM宏和D-cache元数据；不修改库计价。
它可能增加队列压力和cache miss，IPC收益尚未证明；当前不采用、不开始测量，也不宣称面积已经到36,000。
最终配置选择等待ER1六程序基线与源级容量/路径分析，避免参数扫描。

只保存独立候选，主工作区EU及ER1测量副本未改动。两候选均包含同一保留字重命名兼容修复。
没有中间综合、仿真或定向测试。新测试必须先报告完整组合及可观收益依据。
''',encoding='utf-8')
    write(BASE/'source_batch_identity.json',dict(candidates=candidates,report=str(report),report_sha256=sha(report),
                                              new_test_started=False,main_worktree_changed=False))
    print(json.dumps(candidates,ensure_ascii=False))


if __name__=='__main__':main()
