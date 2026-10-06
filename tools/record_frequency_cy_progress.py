"""Record adopted CY identities and structural scope only; never run HDL/EDA."""
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
    if candidate.name!='CY_local_execution_wake' or record['tests_started']:
        raise ValueError('Only record adopted, untested CY')
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    errors=[name for name,digest in record['source_sha256'].items() if sha(MAIN/name)!=digest]
    errors += ['frozen:'+name for name,digest in frozen['snapshot_sha256'].items()
               if sha(run/'source'/name)!=digest]
    if errors:
        raise ValueError('Preserve changed sources: '+str(errors))
    previous=Path('F:/CPU2026Candidates/frequency_research_20261003/CV_lsq_parallel_report_destination')
    measured=Path('F:/CPU2026CourseRuns/architecture_CD1_20261004/source')
    proof={
        'status':'SOURCE_IDENTITIES_ONLY_NO_HDL_TEST',
        'active_source_files':len(record['source_sha256']),
        'frozen_input_files':len(frozen['snapshot_sha256']),
        'changed_rtl_vs_measured_CD1':[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(measured/name)],
        'changed_rtl_vs_CV':[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(previous/name)],
        'tests_started':False,
        'limitations':'File identity and manual source reasoning only; no HDL syntax/function/area/IPC/timing proof',
    }
    record['implementation_report']='E:/Verilog_cpu/reports/frequency_batch_CY_implementation_2026-10-04.md'
    record['source_identity_review']=proof
    RECORD.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=MAIN/'reports/frequency_batch_measurement_2026-10-04.md'
    source=report.read_text(encoding='utf-8')
    anchor='## CY：低排名直接选择与本地取消/早期唤醒，未测试'
    if anchor not in source:
        report.write_text(source+'\n\n'+anchor+'\n\n'+
            '主工作树采用 CY，继承 CV/CU1，再加入 decoded low-rank RS、完整 ALU/MDU 本地恢复取消、真实 MDU busy、ALU/MDU 早期 wake 资格分离。LSQ wake 与全部 completion/PRF/ROB generation 防护保留。十级普通流水、课程版本/容量/延迟仍不变，无新增功能寄存器。157 个冻结输入与 40 个活动源码身份一致；没有启动新 HDL/EDA/仿真测试，所有当前指标未知。详见 [CY 实现报告](E:/Verilog_cpu/reports/frequency_batch_CY_implementation_2026-10-04.md)。\n',encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False))


if __name__=='__main__':
    main()
