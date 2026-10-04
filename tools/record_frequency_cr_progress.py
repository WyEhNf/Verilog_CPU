"""Record adopted CR source identities; never launch HDL/EDA or benchmarks."""
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
    if candidate.name!='CR_icache_control_scan' or record['tests_started']:
        raise ValueError('Only update the adopted, untested CR identity')
    errors=[name for name,digest in record['source_sha256'].items() if sha(MAIN/name)!=digest]
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    errors += ['frozen:'+name for name,digest in frozen['snapshot_sha256'].items()
               if sha(run/'source'/name)!=digest]
    if errors:
        raise ValueError('Preserve changed source: '+str(errors))
    cd1=Path('F:/CPU2026CourseRuns/architecture_CD1_20261004/source')
    cn=Path('F:/CPU2026Candidates/frequency_research_20261003/CN_lsq_request_data_distribution')
    changes_cd1=[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(cd1/name)]
    changes_cn=[name for name in record['source_sha256'] if name.endswith('.v') and sha(MAIN/name)!=sha(cn/name)]
    proof={
        'status':'SOURCE_IDENTITIES_ONLY_NO_HDL_TEST',
        'active_source_files':len(record['source_sha256']),
        'frozen_input_files':len(frozen['snapshot_sha256']),
        'changed_rtl_vs_measured_CD1':changes_cd1,
        'changed_rtl_vs_CN':changes_cn,
        'tests_started':False,
        'limitations':'Identity and source preparation only; no syntax/function/area/IPC/timing proof',
    }
    record['implementation_report']='E:/Verilog_cpu/reports/frequency_batch_CR_implementation_2026-10-04.md'
    record['source_identity_review']=proof
    RECORD.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=MAIN/'reports/frequency_batch_measurement_2026-10-04.md'
    source=report.read_text(encoding='utf-8')
    anchor='## CR：DIV、ROB、MDU 和 Icache 继续重排，仍未测试'
    if anchor not in source:
        report.write_text(source+'\n\n'+anchor+'\n\n'+
            '主工作树更新为 CR，在 CN 上增加四组组合/原边沿写入重排；157-file 课程输入已冻结，CN 备份及 CO/CP/CQ 中间候选保留。十级普通整数流水、容量、课程参数与 SRAM 不变，没有主动增加功能状态。未启动新编译、综合、STA、仿真或形式验证。CR 的 Fmax、IPC、面积和正确性全部未知；最近已测 CD1 数字及 16/19 的失败仍属于旧版本。人工语义推导、负载证据和剩余可行动检查见 [CR 实现报告](E:/Verilog_cpu/reports/frequency_batch_CR_implementation_2026-10-04.md)。\n',encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False))


if __name__=='__main__':
    main()
