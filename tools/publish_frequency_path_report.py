"""Publish the frozen endpoint inventory with per-path RTL advice."""
from pathlib import Path
from collections import Counter
import json, html, re
from report_frequency_paths import AREA, OUT, sha

ROOT=Path('E:/Verilog_cpu')
REPORT=ROOT/'reports/frequency_path_checklist_2026-10-03.html'
MD=ROOT/'reports/frequency_path_checklist_2026-10-03.md'

def short(s):
    for a,b in [('core.g_ooo_backend.backend.',''),('core.g_cached_memory.g_nonblocking_icache.icache.','icache.'),('core.g_cached_memory.g_nonblocking_dcache.dcache.','dcache.'),('core.g_decode_pipeline.pipe.','decode.'),('core.frontend.','frontend.'),('core.g_banked_predictor.predictor.','predictor.')]: s=s.replace(a,b)
    return s

def advice(r):
    e,s=r['end']['rtl'],r['start']['rtl']
    if r['slack_300_ns']>=0:
        return '此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。'
    prefix=''
    if 'recovery_rs_branch_slot' in s:
        prefix='先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；'
    elif '.lsq.head_o' in s:
        prefix='先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；'
    elif 'icache.if_resp_pc_o' in s:
        prefix='先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；'
    elif 'bus.g_response_fifos.data' in s:
        prefix='先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；'
    if '.lsq.' in e:
        if any(n in e for n in ('addr_mem','mask_mem','addr_ready')):
            body='把 LSQ 地址、掩码、ready 状态改为每行独立写端口，静态译码分配/early-AGU/执行更新，并保持原同拍写优先级和 generation 校验。'
        elif any(n in e for n in ('forward_','complete_value')):
            body='将前递/完成数据与有效位分开存储，逐行选择写源，避免全队列广播清零和宽数据写使能。'
        elif any(n in e for n in ('head_o','tail_o','occupancy')):
            body='采用窄位宽入队/出队计数与并行 pop 判断，保持循环队列占用和回收语义。'
        else:
            body='逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。'
    elif '.rs.' in e:
        if 'value_mem' in e:
            body='将 RS 每行操作数写源选择与 kill/valid 分离，局部处理 allocation/wakeup；保留恢复时存活指令的同拍唤醒。'
        else:
            body='对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。'
    elif 'decode' in e:
        body='在已有环形译码缓冲上局部生成行写/头尾计数使能，缩短 recovery→ready→consume 链；如增加 credit/skid 缓冲，保持每拍接收能力。'
    elif 'frontend' in e:
        body='将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。'
    elif '.rob.' in e:
        body='逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。'
    elif '.prf.' in e:
        body='将 ready 位和数据写端口分开，按物理寄存器行译码 allocate/writeback/reclaim，减少全局恢复信号直接负载。'
    elif '.rename.' in e:
        body='对 free bitmap/RAT 做分组恢复及并行计数，隔离恢复选择与正常重命名写使能，保留同拍回收/分配优先级。'
    elif 'icache' in e:
        if 'fakeram' in r['end']['kind']:
            body='分别局部生成 SRAM CE/WE/地址，区分 hit 与 refill；必要时寄存完整 SRAM 命令，但不能只延迟地址而错开控制。'
        elif 'state_bank' in e:
            body='已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。'
        else:
            body='拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。'
    elif 'dcache' in e:
        if 'fakeram' in r['end']['kind']:
            body='在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。'
        elif 'metadata' in e:
            body='在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。'
        elif 'mshr' in e or 'waiter' in e:
            body='按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。'
        else:
            body='分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。'
    elif 'mdu' in e:
        if 'cache_q_reg' in e or 'cache_r_reg' in e:
            body='缩短除法商/余数结果选择和符号修正逻辑；可把修正与缓存写入分开一拍，但需评估 DIV/REM 延迟对 IPC 的影响。'
        else:
            body='优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。'
    elif '.g_alu' in e:
        body='把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。'
    elif 'predictor' in e or 'ras_' in e:
        body='按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。'
    elif 'completion' in e:
        body='局部保存完成项并分离仲裁选择与消费许可，采用平衡仲裁和独立保持槽，切断跨功能单元的 ready 广播链。'
    elif 'bus.' in e or 'memory_bridge' in e:
        body='用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。'
    elif 'instret' in e:
        body='用局部并行退休计数驱动窄增量加法，先修共享提交/恢复控制；退休计数仍须精确。'
    elif 'mmio' in e:
        body='局部保存 MMIO ack 与标签，分离 valid 消费和标签载荷更新；仍在合法写完成握手后产生退出副作用。'
    else:
        body='对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。'
    return prefix+body

def main():
    rows=json.loads((OUT/'resolved_inventory.json').read_text())
    reps=json.loads((OUT/'representatives.json').read_text())
    cells=json.loads((OUT/'cell_identity.json').read_text())
    counts=Counter(r['family'] for r in rows)
    byfamily={r['family']:r for r in reps}
    maxerror=0
    for r in reps:
        checks=json.loads((OUT/f"family_{r['representative_id']:04}.json").read_text())['checks']
        assert len(checks)==1
        c=checks[0]; assert c['endpoint']==r['endpoint'] and c['startpoint']==r['startpoint']
        assert c.get('source_clock_edge','rise')=='rise'
        assert c.get('target_clock_edge','rise')=='rise'
        maxerror=max(maxerror,abs(c['data_arrival_time']*1e9-r['arrival_ns']))
        stages=[]
        pts=c['source_path']
        for i,v in enumerate(pts):
            info=cells.get(v['instance'],{}); pin=v['pin'].rsplit('/',1)[-1]
            if pin not in info.get('outputs',{}): continue
            if i and pts[i-1]['instance']!=v['instance']: continue
            delta=(v['arrival']-(pts[i-1]['arrival'] if i else 0))*1e9
            stages.append(dict(pin=v['pin'],cell=v['cell'],delay_ns=round(delta,6),
                cap_ff=round(v.get('capacitance',0)*1e15,4),local_module_fanout=info['outputs'][pin]))
        r['stages']=stages
        r['largest_stages']=sorted(stages,key=lambda x:x['delay_ns'],reverse=True)[:3]
        r['count']=counts[r['family']]
        r['suggestion']=advice(r)
    assert maxerror<0.006,maxerror # JSON has four significant figures; TSV uses full numeric values.
    for r in rows:
        r['family_id']=byfamily[r['family']]['representative_id']
        r['suggestion']=advice(r)
    assert all(rows[i]['arrival_ns']>=rows[i+1]['arrival_ns'] for i in range(len(rows)-1))
    assert all(r['suggestion'] for r in rows)
    result=dict(status='COMPLETE',scope='One worst setup path per timed endpoint, not every combinatorial alternative',
        paths=len(rows),families=len(reps),slow_at_300=sum(r['slack_300_ns']<0 for r in rows),
        slow_families_at_300=sum(r['slack_300_ns']<0 for r in reps),
        netlist_sha256=sha(AREA/'mapped.v'),max_json_rounding_error_ns=maxerror,
        target_period_ns=10/3,original_sdc_period_ns=2,unchanged_netlist_and_constraints=True,
        source='Existing complete hierarchical identity proof plus frozen mapped netlist and SDC',
        input_sha256={str(p):sha(p) for p in [AREA/'mapped.v',AREA/'constraints.sdc',OUT/'endpoint_paths.tsv',OUT/'representatives.json',OUT/'cell_identity.json']})
    for lib in json.loads((AREA/'area_audit.json').read_text())['libraries']:
        assert sha(lib['path'])==lib['sha256']
        result['input_sha256'][lib['path']]=lib['sha256']
    original=json.loads((OUT/'inventory_inputs.json').read_text())
    for p,h in original.items(): assert sha(p)==h
    (OUT/'all_paths_with_advice.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'families_with_advice.json').write_text(json.dumps(reps,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    selected=[1,2,3,4,5,6,19,31,32,38,40,45,48,65,66,82,95,103,104,108,124,150,194,278,311,333]
    md=['# 2026-10-03 综合后路径检查清单','',
        '检查对象：已采用的 8 级组合参数配置，整机 Fmax **53.439 MHz**、最小周期 **18.712891 ns**。本次仅分析冻结网表，未修改 RTL。',
        '',f"已检查 **{len(rows):,} 个有约束且存在可达时序路径的终点**，每个终点保留最差 setup 路径；归并为 **{len(reps)} 类终点字段**，其中 **{result['slow_at_300']:,} 条**在 300 MHz 下 setup slack 为负。字段归类不表示独立根因，同一控制链可影响多个字段。",'',
        '按数据到达时间降序排序。寄存器路径耗时包含 clk→Q、组合逻辑及库负载效应，不含终点 setup/时钟不确定度；接口路径包含所设输入延迟。300 MHz 的 3.333333 ns 还要留 setup、0.05 ns uncertainty 及接口输出延迟。清单按原 2 ns SDC 的 slack 平移 1.333333 ns；已核对代表路径为同一上升沿单周期时钟。', '',
        '这是完整终点最差路径清单，不是枚举所有组合逻辑路径。无路径/常量终点不在清单中。使用原 ASAP7 TT 库、全部 SRAM 与层级、原约束及 reset=0；check_setup 通过。频率仍是综合后理想时钟估计，不是布局布线结果。','',
        f'[打开可搜索完整清单]({REPORT.as_posix()}) · [37,523 条原始数值与逐条建议]({(OUT/"all_paths_with_advice.json").as_posix()}) · [368 类详细门延迟]({(OUT/"families_with_advice.json").as_posix()})','',
        '| 类别编号 | 代表路径（RTL 起点 → 终点） | 耗时/ns | 修改建议 |','|---:|---|---:|---|']
    for n in selected:
        r=reps[n-1]
        md.append(f"| {n} | `{short(r['start']['rtl'])}` → `{short(r['end']['rtl'])}` | {r['arrival_ns']:.3f} | {r['suggestion']} |")
    md += ['', '实测共享瓶颈：', '',
        '- LSQ 最慢路径：`_477118_/Y` 的 NOR5 门约 4.890 ns，输出负载 253.4 fF、模块内接收引脚 599；另一门 `_380941_/Y` 约 2.471 ns。应先局部化真实行状态和写控制。',
        '- 恢复路径：`_333051_/Y` 对应 `frontend.redirect_valid_i`，约 3.106 ns；`_361420_/Y` 对应译码缓冲 `flush_i`，约 5.118 ns、410.7 fF。恢复信号经过前端/译码后仍影响 RS，不能仅在 ALU 数据路径加级。',
        '- Icache 路径已映射出 `frontend.if_req_pc_o` → `request_match_found` → `frontend.req_fire`，对应 RTL 的 `response_can_chain` 同周期再发请求。直接禁用该机制可能损失 IPC。',
        '- Dcache 路径已映射出 `refill_array_write` → `static_request_action` → 元数据 bank，中央动作编码的一个门约 3.930 ns；局部元数据门另占约 2.949 ns。', '',
        '建议先做 LSQ 行写控制、恢复信号局部分发，再处理前端/Icache 同周期链与 Dcache 动作分发。普通整数流水线已有 8 级，但这些跨级 ready/flush 控制仍可形成长路径。所有建议是待验证的修改方向，没有预先承诺频率收益。', '',
        '固定基准保持不变：面积 46789.856634 µm²、IPC 1.1182750169703988。当前面积 46298.423154 µm²（−1.0503%）、IPC 1.0087820702582486（−9.7912%）；IPC 下限 1.0064475152733589，仅余约 0.2314% 相对下降空间。优先不增加周期的局部重构；新增阶段须复测面积和 IPC。', '',
        '完整逐类降序清单：','', '| 类别 | 路径 | 耗时/ns | 终点数 | 修改建议 |','|---:|---|---:|---:|---|']
    for r in reps:
        md.append(f"| {r['representative_id']} | `{short(r['start']['rtl'])}` → `{short(r['end']['rtl'])}` | {r['arrival_ns']:.3f} | {r['count']} | {r['suggestion']} |")
    MD.write_text('\n'.join(md)+'\n',encoding='utf-8')
    # Compact, self-contained HTML: full path advice is shared by identical text only.
    suggestions=list(dict.fromkeys(r['suggestion'] for r in rows)); advice_ids={v:i for i,v in enumerate(suggestions)}
    data=dict(summary=result,advice=suggestions,
        rows=[[r['rank'],round(r['arrival_ns'],6),round(r['slack_300_ns'],6),short(r['start']['rtl']),short(r['end']['rtl']),r['family_id'],advice_ids[r['suggestion']],r['startpoint'],r['endpoint']] for r in rows],
        families=[[r['representative_id'],r['count'],r['rank'],r['largest_stages'],r['stages']] for r in reps])
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CPU 路径检查 · 2026-10-03</title>
<style>body{font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif;background:#f5f7fa;color:#183044;margin:24px}h1{font-size:27px}header,nav,article{background:white;border:1px solid #dce3eb;border-radius:10px;padding:18px;margin-bottom:16px}p{max-width:1200px}input,select,button{font:inherit;padding:8px;border:1px solid #bbc9d5;border-radius:5px;background:white;margin:4px}input{width:400px;max-width:90%}table{border-collapse:collapse;width:100%;background:white;font-size:13px}th,td{padding:9px;border:1px solid #e0e6ec;text-align:left;vertical-align:top}th{background:#e6eef5;position:sticky;top:0}td{overflow-wrap:anywhere}td.path{max-width:420px}td.advice{min-width:280px;max-width:600px}.bad{color:#b12f24}.good{color:#1b7550}.num{font-variant-numeric:tabular-nums;white-space:nowrap}code{font-size:12px}details{margin:6px 0}summary{cursor:pointer;color:#175e87}.muted{color:#526779}.scroll{overflow:auto}a{color:#126093}</style>
<header><h1>CPU 路径检查清单</h1><p><b>2026-10-03 · 已采用的 8 级组合配置 · 53.439 MHz</b><br>37,523 个终点的最差 setup 路径，归并为 368 类字段。按数据耗时降序，35,662 条在 300 MHz 下 setup slack 为负。同一控制链可出现在多类字段中。</p>
<p>数据耗时包含 clk→Q 和组合延迟；3.333333 ns 周期还需留出 setup、0.05 ns 时钟不确定度和接口约束。原 2 ns SDC 的 slack 平移至 300 MHz。使用全部 SRAM、原网表、原库与约束；仅重新分析，未修改 RTL。这是综合后理想时钟估计，无布线寄生。</p>
<p>优先处理 LSQ 行写控制、恢复/清空信号分发、Icache 同周期请求链和 Dcache 动作编码。当前 IPC 距允许下限只余约 0.23%，新增周期必须复测。建议基于端点归属、代表门路径和 RTL 审查；同类路径共享建议，不代表每条组合逻辑替代路径都已枚举。</p></header>
<nav><select id="mode"><option value="family">368 类代表路径</option><option value="all">37,523 条终点路径</option></select><input id="q" placeholder="搜索 RTL 名称、网表引脚、修改建议"><label><input type="checkbox" id="slow" style="width:auto">仅看 300 MHz 未通过</label><div><button id="prev">上一页</button><span id="status"></span><button id="next">下一页</button></div></nav>
<div class="scroll"><table><thead><tr><th>全局排名 / 类别</th><th>耗时 ns ↓</th><th>300 MHz slack ns</th><th>RTL 起点 → 终点</th><th>修改建议</th><th>代表门路径证据</th></tr></thead><tbody id="body"></tbody></table></div>
<p class="muted">门延迟来自 OpenSTA JSON 相邻输入/输出到达时间之差，受其四位有效数字精度影响；单元负载为 STA 电容，fanout 为该模块内接收引脚数（跨层级负载不能直接等同）。详细路径为该类最慢代表，不能当作此类其他终点的逐门数据。</p>
<script type="application/json" id="data">PAYLOAD</script><script>
const d=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);let page=0;const size=75, fm=new Map(d.families.map(f=>[f[0],f]));
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(){const q=$('q').value.toLowerCase(), mode=$('mode').value;let rows=mode==='all'?d.rows:d.families.map(f=>d.rows[f[2]-1]);rows=rows.filter(r=>(!$('slow').checked||r[2]<0)&&(!q||(r[3]+' '+r[4]+' '+r[7]+' '+r[8]+' '+d.advice[r[6]]).toLowerCase().includes(q)));page=Math.max(0,Math.min(page,Math.ceil(rows.length/size)-1));$('status').textContent=` ${rows.length.toLocaleString()} 条 · 第 ${page+1} / ${Math.max(1,Math.ceil(rows.length/size))} 页 `;$('prev').disabled=page===0;$('next').disabled=(page+1)*size>=rows.length;
$('body').innerHTML=rows.slice(page*size,(page+1)*size).map(r=>{const f=fm.get(r[5]),st=f[3],detail=f[4].map(s=>`<tr><td><code>${esc(s.pin)}</code><br>${esc(s.cell)}</td><td>${s.delay_ns.toFixed(3)}</td><td>${s.cap_ff.toFixed(2)}</td><td>${s.local_module_fanout}</td></tr>`).join('');return `<tr><td class="num">#${r[0]} / C${r[5]}<br>同类 ${f[1]} 个终点</td><td class="num">${r[1].toFixed(3)}</td><td class="num ${r[2]<0?'bad':'good'}">${r[2].toFixed(3)}</td><td class="path"><code>${esc(r[3])}</code><br>↓<br><code>${esc(r[4])}</code><details><summary>原网表引脚</summary>${esc(r[7])}<br>→ ${esc(r[8])}</details></td><td class="advice">${esc(d.advice[r[6]])}</td><td>${st.map(s=>`<code>${esc(s.pin)}</code><br>${s.delay_ns.toFixed(3)} ns / ${s.cap_ff.toFixed(1)} fF`).join('<hr>')}<details><summary>C${r[5]} 最慢代表的全部单元段</summary><table><tr><th>单元输出</th><th>ns</th><th>fF</th><th>模块内 fanout</th></tr>${detail}</table></details></td></tr>`}).join('')}
for(const id of ['q','mode','slow'])$(id).addEventListener('input',()=>{page=0;render()});$('prev').onclick=()=>{page--;render()};$('next').onclick=()=>{page++;render()};render();</script></html>'''.replace('PAYLOAD',payload)
    REPORT.write_text(page,encoding='utf-8')
    result['output_sha256']={str(p):sha(p) for p in [REPORT,MD,OUT/'all_paths_with_advice.json',OUT/'families_with_advice.json']}
    (OUT/'report_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
