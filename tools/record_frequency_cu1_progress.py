"""Record adopted CU1 identities and source deltas; no HDL/EDA/benchmarks."""
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
    if candidate.name!='CU1_rob_reclaim_width_guard' or record['tests_started']:
        raise ValueError('Only update adopted, untested CU1')
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    errors=[name for name,digest in record['source_sha256'].items() if sha(MAIN/name)!=digest]
    errors += ['frozen:'+name for name,digest in frozen['snapshot_sha256'].items()
               if sha(run/'source'/name)!=digest]
    if errors:
        raise ValueError('Preserve changed source: '+str(errors))
    cn=Path('F:/CPU2026Candidates/frequency_research_20261003/CN_lsq_request_data_distribution')
    cd1=Path('F:/CPU2026CourseRuns/architecture_CD1_20261004/source')
    proof={
        'status':'SOURCE_IDENTITIES_ONLY_NO_HDL_TEST',
        'active_source_files':len(record['source_sha256']),
        'frozen_input_files':len(frozen['snapshot_sha256']),
        'changed_rtl_vs_measured_CD1':[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(cd1/name)],
        'changed_rtl_vs_CN':[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(cn/name)],
        'tests_started':False,
        'limitations':'Identity and manual source preparation only; no syntax/function/area/IPC/timing proof',
    }
    record['implementation_report']='E:/Verilog_cpu/reports/frequency_batch_CU1_implementation_2026-10-04.md'
    record['source_identity_review']=proof
    RECORD.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=MAIN/'reports/frequency_batch_measurement_2026-10-04.md'
    source=report.read_text(encoding='utf-8')
    anchor='## CU1：MUL、Dcache tag 端口与 ROB reclaim 继续重排，仍未测试'
    if anchor not in source:
        report.write_text(source+'\n\n'+anchor+'\n\n'+
            '主工作树采用 CU1，继承 CR 并增加三组结构修改；157-file 输入和 CR 备份已保存。十级普通整数流水、功能状态位数、课程参数/版本/延迟不变，按课程 fakeram lane 规则保留 tag SRAM 宏形状与数量。源码身份核对通过，但没有启动任何新 HDL/EDA/仿真测试，所有 CU1 指标未知。负载证据、源码推导和剩余方向见 [CU1 实现报告](E:/Verilog_cpu/reports/frequency_batch_CU1_implementation_2026-10-04.md)。\n',encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False))


if __name__=='__main__':
    main()
