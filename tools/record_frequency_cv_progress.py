"""Record CV source identities and deltas only; no HDL/EDA/benchmarks."""
import hashlib
import json
from pathlib import Path


MAIN=Path('E:/Verilog_cpu')
RECORD=MAIN/'build/cpu2026/active_frequency_implementation_20261004.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    record=json.loads(RECORD.read_text(encoding='utf-8'))
    candidate=Path(record['candidate'])
    run=Path(record['frozen_run'])
    if candidate.name!='CV_lsq_parallel_report_destination' or record['tests_started']:
        raise ValueError('Only record adopted, untested CV')
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    errors=[name for name,digest in record['source_sha256'].items() if sha(MAIN/name)!=digest]
    errors += ['frozen:'+name for name,digest in frozen['snapshot_sha256'].items()
               if sha(run/'source'/name)!=digest]
    if errors:
        raise ValueError('Preserve changed source: '+str(errors))
    root=Path('F:/CPU2026Candidates/frequency_research_20261003')
    previous=root/'CU1_rob_reclaim_width_guard'
    measured=Path('F:/CPU2026CourseRuns/architecture_CD1_20261004/source')
    proof={
        'status':'SOURCE_IDENTITIES_ONLY_NO_HDL_TEST',
        'active_source_files':len(record['source_sha256']),
        'frozen_input_files':len(frozen['snapshot_sha256']),
        'changed_rtl_vs_measured_CD1':[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(measured/name)],
        'changed_rtl_vs_CU1':[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(previous/name)],
        'tests_started':False,
        'limitations':'File identity and manual source reasoning only; no syntax/function/area/IPC/timing proof',
    }
    record['implementation_report']='E:/Verilog_cpu/reports/frequency_batch_CV_implementation_2026-10-04.md'
    record['source_identity_review']=proof
    RECORD.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=MAIN/'reports/frequency_batch_measurement_2026-10-04.md'
    source=report.read_text(encoding='utf-8')
    anchor='## CV：LSQ report 与物理目的并行选择，未测试'
    if anchor not in source:
        report.write_text(source+'\n\n'+anchor+'\n\n'+
            '主工作树采用 CV，继承 CU1 并融合 LSQ report/目的选择。原 96 位物理表移入 LSQ，删除返回后的第二次读取，report 67→73 位但分组仍五个；无新增寄存器或周期。源码和 157 个冻结输入身份一致，没有启动新硬件测试。当前指标全部未知，最近 CD1 测量独立保留。详见 [CV 实现报告](E:/Verilog_cpu/reports/frequency_batch_CV_implementation_2026-10-04.md)。\n',encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False))


if __name__=='__main__':
    main()
