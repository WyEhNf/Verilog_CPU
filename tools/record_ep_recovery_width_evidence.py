"""Attach the read-only elaboration evidence; do not alter frozen RTL/tools."""
import hashlib
import json
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=json.loads(active_path.read_text(encoding='utf-8'))
    proof=Path('F:/CPU2026Proofs/EP_recovery_port_width_review_20261005.json')
    data=json.loads(proof.read_text(encoding='utf-8'))
    assert data['all_selected_fields_connected_exactly']
    assert data['input_sha256']==sha(data['input'])
    assert Path(active['frozen_run'])==Path('F:/CPU2026CourseRuns/architecture_EP_20261005')
    assert sha(active['pretest_report'])==active['pretest_report_sha256']
    report=Path(active['post_dispatch_source_research']['report'])
    text=report.read_text(encoding='utf-8')
    assert '\n## 恢复位宽告警的既有展开接线证据\n' not in text
    text+='''\n## 恢复位宽告警的既有展开接线证据\n\nEP和EL1原综合日志都有recovery_saved_owner输入128→76、recovery_query_tree输入46→21告警。只读EL1映射，query第7–13位精确来自chosen_age低7位，第14–19位来自head视图，第20位来自preview视图，不能据告警字面推断head/preview被截掉。再只读正在运行EP已生成的elaborated.json：具体ROB参数slot6/count7，query signal_i恰为occupancy7+chosen_age低7+head6+preview1共21位；saved data_i恰为kill64+chosen_age低6+chosen_slot低6共76位。所有公共bit ID逐项一致。\n\n此证据消除了“这两个字段包因告警而漏接”的具体怀疑，未重新调用Yosys或任何测试，不证明整个branch recovery/映射功能等价；原程序测试仍未运行。Dcache action包17位输入与16位接收字段的源码拼接中，多的一位是未使用高位padding，不是删除reset字段；暂不因告警盲改宽度。没有调整课程工具或冻结输入。\n\n展开接线证据：`F:/CPU2026Proofs/EP_recovery_port_width_review_20261005.json`；映射查询input证据：`F:/CPU2026Proofs/EL1_recovery_cast_ports_20261005.json`。\n'''
    report.write_text(text,encoding='utf-8')
    active['post_dispatch_source_research'].update(report_sha256=sha(report),
        recovery_width_evidence=str(proof),recovery_width_evidence_sha256=sha(proof),
        recovery_query_and_saved_port_fields_exact=True,
        evidence_scope='Existing saved elaboration/mapped port bits only; no full recovery proof, no additional EDA or program test.')
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(report),recovery_evidence=str(proof),
        query_bits=21,saved_bits=76,fields_exact=True,frozen_source_unchanged=True,new_tests_started=False)))


if __name__=='__main__':
    main()
