"""Record adopted DD identities and source scope; never run HDL/EDA."""
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
    if candidate.name!='DD_lsq_circular_hazards' or record['tests_started']:
        raise ValueError('Only record adopted, untested DD')
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    errors=[name for name,digest in record['source_sha256'].items() if sha(MAIN/name)!=digest]
    errors+=['frozen:'+name for name,digest in frozen['snapshot_sha256'].items()
             if sha(run/'source'/name)!=digest]
    if errors:
        raise ValueError('Preserve changed sources: '+str(errors))
    previous=Path('F:/CPU2026Candidates/frequency_research_20261003/CY_local_execution_wake')
    measured=Path('F:/CPU2026CourseRuns/architecture_CD1_20261004/source')
    proof={
        'status':'SOURCE_IDENTITIES_ONLY_NO_HDL_TEST',
        'active_source_files':len(record['source_sha256']),
        'frozen_input_files':len(frozen['snapshot_sha256']),
        'changed_rtl_vs_measured_CD1':[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(measured/name)],
        'changed_rtl_vs_CY':[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(previous/name)],
        'tests_started':False,
        'limitations':'File identity and manual source reasoning only; no HDL syntax/function/area/IPC/timing proof',
    }
    record['implementation_report']='E:/Verilog_cpu/reports/frequency_batch_DD_implementation_2026-10-05.md'
    record['source_identity_review']=proof
    record['pretest_report']='E:/Verilog_cpu/reports/frequency_batch_DD_pretest_2026-10-05.md'
    RECORD.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    timeline=MAIN/'reports/frequency_batch_measurement_2026-10-04.md'
    source=timeline.read_text(encoding='utf-8')
    anchor='## DD：2026-10-05，算术与 LSQ 环形顺序继续重排，未测试'
    if anchor not in source:
        timeline.write_text(source+'\n\n'+anchor+'\n\n'+
            '主工作树采用 DD，继承 CY 并加入 carry-select tails、radix4 Booth 三/三层 CSA、load 本地 wake、LSQ 一位环形顺序 tournament 与静态 hazard 化简。十级普通流水、课程 39 项配置/版本/容量/内存延迟 10 保留；MUL S1 少声明 128 位，实际面积未知。40 个活动源码和 157 个冻结输入身份一致；没有启动新 HDL/EDA/仿真测试，所有当前指标未知。详见 [DD 实现报告](E:/Verilog_cpu/reports/frequency_batch_DD_implementation_2026-10-05.md)与 [测试前报告](E:/Verilog_cpu/reports/frequency_batch_DD_pretest_2026-10-05.md)。\n',encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False))


if __name__=='__main__':
    main()
