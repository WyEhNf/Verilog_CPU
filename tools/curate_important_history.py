"""Keep significant CPU versions and grouped changes in a bounded Git history."""
import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import pickle
import re
import subprocess
import sys

ROOT=pathlib.Path('E:/Verilog_cpu')
INPUT=pathlib.Path('F:/CPU2026History/reconstruction_20261006')
WORK=pathlib.Path('F:/CPU2026History/important_versions')
OUT=ROOT/'history/important_versions'
BASE='b9e7fc2cadfbed11ee960ffdc0e3ac432a7cbb13'
BRANCH_MAIN='codex/important-development-history'
BRANCH_VERSIONS='codex/important-research-versions'
BRANCH_FINAL='codex/important-history'

def log(s):print(s,flush=True)

def git(*args,data=None):
    r=subprocess.run(['git',*args],cwd=ROOT,input=data,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf-8','replace'))
    return r.stdout

def dump(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def pathnorm(s):return str(s).replace('\\','/').rstrip('/')

def digest(b):return hashlib.sha256(b).hexdigest()

def tree(oid):
    out={}
    for entry in git('ls-tree','-rz',oid).split(b'\0'):
        if entry:
            info,p=entry.split(b'\t',1);mode,kind,obj=info.decode().split()
            if kind=='blob':out[p.decode('utf-8')]=(mode,obj)
    return out

def classify(p):
    n=pathlib.Path(p).name.lower()
    if p.startswith(('tb/','tests/')) or p.startswith('tools/') and n.startswith(('test_','prove_')):return 'test'
    if p.startswith(('docs/','reports/')) or p in ('STATUS.md','README.md','plan.md','instructions.md','lead-in.md'):return 'docs'
    if p.startswith('rtl/'):return 'source'
    return 'chore'

def source_type(intent):
    s=intent.lower()
    if re.search(r'修复|修正|纠正|根因|卡死|永久|\bfix\b|incorrect|deadlock|\brepair\b',s):return 'fix'
    if re.search(r'优化|面积|频率|并行|缩短|流水|area|timing|parallel|bank|pipeline|optim|fanout',s):return 'perf'
    return 'feat'

class Stream:
    def __init__(self,p):
        self.f=p.open('wb');self.mark=1;self.blobs={};self.states={};self.records=[]
        self.name=git('config','user.name').decode('utf-8').strip();self.email=git('config','user.email').decode().strip()
    def put(self,b):
        oid=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if oid not in self.blobs:
            n=self.mark;self.mark+=1;self.blobs[oid]=n
            self.f.write(f'blob\nmark :{n}\ndata {len(b)}\n'.encode()+b+b'\n')
        return oid
    def commit(self,branch,parent,changes,title,t,body='',merges=()):
        state=dict(self.states.get(parent,{}));actual={}
        for p,v in changes.items():
            if isinstance(v,bytes):v=('100644',self.put(v))
            if state.get(p)!=v:actual[p]=v
        if not actual:return parent
        n=self.mark;self.mark+=1
        epoch=int(dt.datetime.fromisoformat(t.replace('Z','+00:00')).timestamp())
        msg=(title+'\n\n'+body.strip()+'\n').encode('utf-8')
        self.f.write(f'commit refs/heads/{branch}\nmark :{n}\nauthor {self.name} <{self.email}> {epoch} +0000\ncommitter {self.name} <{self.email}> {epoch} +0000\ndata {len(msg)}\n'.encode()+msg+b'\n')
        if parent:self.f.write(f'from {parent}\n'.encode())
        for m in dict.fromkeys(merges):
            if m and m!=parent:self.f.write(f'merge {m}\n'.encode())
        for p,v in sorted(actual.items()):
            qp=json.dumps(p,ensure_ascii=False)
            if v is None:self.f.write(f'D {qp}\n'.encode());state.pop(p,None)
            else:
                mode,obj=v;self.f.write(f'M {mode} {obj} {qp}\n'.encode());state[p]=v
        self.f.write(b'\n');ref=':'+str(n);self.states[ref]=state
        self.records.append({'commit':ref,'type':title.split('(',1)[0],'subject':title,'paths':sorted(actual)})
        return ref
    def finish(self):self.f.write(b'done\n');self.f.close()

def title_for(e,label):
    text=e.get('public_intent','')
    patterns=[('P8b','P8b ROB PC lookup'),('P8','P8 ROB reclaim metadata'),('P7','P7 free bitmap'),('P6','P6 metadata ownership'),('P5','P5 narrow store payload'),('Wallace','Wallace multiplier'),('稀疏','sparse LSQ allocation'),('JAL/JALR','jump link writeback'),('非阻塞','nonblocking cache'),('共享','shared datapath'),('SRAM','SRAM integration'),('半字','halfword ISA support'),('MMIO','MMIO halt protocol'),('RAT','RAT recovery'),('重命名','rename allocation'),('转发','store forwarding'),('回收','ROB reclaim'),('LSQ','LSQ scheduling'),('ROB','ROB recovery'),('PRF','PRF storage'),('预测','branch prediction')]
    for needle,subject in patterns:
        if needle in text:return label+' '+subject
    rtl=[p for p in e['changes'] if p.startswith('rtl/')]
    name=pathlib.Path(rtl[0]).stem if rtl else 'project support'
    return label+' '+name

def plan():
    WORK.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    if git('status','--porcelain=v1','--untracked-files=no').strip():raise RuntimeError('Tracked working files changed')
    original=git('rev-parse','HEAD').decode().strip()
    oldrefs={}
    for line in git('for-each-ref','--format=%(refname) %(objectname)','refs/heads/codex/history-*').decode().splitlines():
        ref,oid=line.split();oldrefs[ref]=oid
    with (INPUT/'enriched_inventory.pickle').open('rb') as f:d=pickle.load(f)
    oldcatalog=json.loads((ROOT/'history/reconstruction_20261006/patch_catalog.json').read_text(encoding='utf-8'))
    markers={(x['session'],x['event_id']):(x['commits'][-1] if x['commits'] else x['context_checkpoint']) for x in oldcatalog}
    # Merge small edits into meaningful development stages, retaining semantic fixes.
    stages=[];current=[];intent=None;has_rtl=False
    for idx,e in enumerate(d['events']):
        if not ('2026-09-05'<=e['time']<'2026-09-28'):continue
        rtl=any(p.startswith('rtl/') and (idx,p) in d['resolved'] for p in e['changes'])
        ei=e.get('public_intent','')
        if rtl and has_rtl and (ei!=intent or e['time'][:10]!=current[0][1]['time'][:10]):
            stages.append(current);current=[];has_rtl=False
        current.append((idx,e))
        if rtl:has_rtl=True;intent=ei
    if current:stages.append(current)
    # Later adopted CPU changes and accompanying tools are grouped by day.
    later=collections.defaultdict(list)
    for idx,e in enumerate(d['events']):
        if e['time']>='2026-09-28':later[e['time'][:10]].append((idx,e))
    stages.extend(later[k] for k in sorted(later))
    w=Stream(WORK/'important.fastimport')
    early_base=git('rev-parse','dc65475').decode().strip()
    for oid in (BASE,early_base,original):w.states[oid]=tree(oid)
    parent=early_base;development=[]
    for number,stage in enumerate(stages,1):
        source_events=[e for idx,e in stage if any(p.startswith('rtl/') and (idx,p) in d['resolved'] for p in e['changes'])]
        first=source_events[0] if source_events else stage[0][1]
        label='V'+str(number).zfill(3)
        desc=title_for(first,label);t=stage[-1][1]['time']
        groups=collections.defaultdict(dict)
        for idx,e in stage:
            for p in e['changes']:
                if (idx,p) in d['resolved']:groups[classify(p)][p]=d['resolved'][(idx,p)][1]
        # Use the recorded complete RTL objects at the stage endpoint, including restored contexts.
        endpoint=next((markers.get((e['session'],e['event_id'])) for _,e in reversed(stage) if markers.get((e['session'],e['event_id']))),None)
        if source_events and endpoint:
            groups['source'].update({p:v for p,v in tree(endpoint).items() if p.startswith('rtl/') or p=='rv32im_defs.vh'})
        refs=[]
        for typ in ('source','test','chore','docs'):
            changes=groups[typ]
            if not changes:continue
            ct=source_type(first.get('public_intent','')) if typ=='source' else typ
            purpose={'source':'implement '+desc,'test':'group '+desc+' verification coverage','chore':'group '+desc+' tooling and configuration','docs':'document '+desc+' design and results'}[typ]
            old=parent;parent=w.commit(BRANCH_MAIN,parent,changes,ct+'(cpu): '+purpose,t)
            if parent!=old:refs.append(parent)
        if refs:development.append({'version':label,'name':desc,'commits':refs})
    main_tip=parent
    # Prioritize native measured candidates and substantial architectural changes.
    selected=[];seen=set()
    def add(v):
        sourcehash={p:digest(b) for p,b in sorted(v['source'].items()) if p.startswith('rtl/') or p=='rv32im_defs.vh'}
        config=v['data'].get('parameter_overrides',v['data'].get('parameters',{}))
        key=(json.dumps(sourcehash,sort_keys=True),json.dumps(config,sort_keys=True))
        if sourcehash and key not in seen:selected.append(v);seen.add(key)
    native=[v for v in d['versions'] if v['id'].startswith('CPU2026CourseRuns') and pathlib.Path(v['path']).parent.name.startswith(('architecture_','ER1_A','ER1_native_identifier','current_adopted')) and not any(x in pathlib.Path(v['path']).parent.name for x in ('closing','budget','readme'))]
    for v in sorted(native,key=lambda x:x['time']):add(v)
    native_roots={pathnorm(v['data'].get('candidate','')).lower() for v in native}
    component_names={'pipeline8_20261003','static_datapath_integration_20261003','frequency_combined_v2_20261003','legal_addi_fix_20261003','control_islands_v2_20261003','rs_age_order_matrix_20261003','rs_age_width_20261003','functional_hierarchy_fixed_20261003','icache_refill_policy_20261003','completion_rank_v8_20261003','dcache_metadata_geometry_20261003','rob_parallel_completion_v3_20261003','icache_parallel_match_integration_20261003','frontend_chain_tradeoff_20261003'}
    for v in sorted(d['versions'],key=lambda x:x['time']):
        name=v['id'].split('__')[-1];root=pathnorm(pathlib.Path(v['path']).parent).lower()
        if v['id'].startswith('CPU2026Candidates__frequency_research') and re.match(r'^(A|B|C|D|E|F|G|H|I|J|K|M|P|Q|AA)_',name) and root not in native_roots:add(v)
        elif v['id'].startswith('CPU2026Candidates__tier3') and re.match(r'^A(1|2|3|23|28|49|63|78|87|96|103|108|109)_',name) and root not in native_roots:add(v)
        elif v['id'].startswith('CPU2026Candidates__') and name in component_names:add(v)
        elif v['id'].startswith('CPU2026Builds__') and any(x in v['id'] for x in ('dc0integrated','rsmeta1dc0','sharedagu_os_nodfg')):add(v)
    all_roots={pathnorm(pathlib.Path(v['path']).parent).lower():v for v in d['versions'] if v['id'].startswith('CPU2026Candidates__')}
    root_map={pathnorm(v['data'].get('candidate',pathlib.Path(v['path']).parent)).lower():v for v in selected}
    parents={}
    for v in selected:
        root=pathnorm(v['data'].get('candidate',pathlib.Path(v['path']).parent)).lower()
        rv=all_roots.get(root,v);p=pathnorm(rv.get('parent_path','')).lower();walk=set()
        while p and p not in walk:
            walk.add(p)
            if p in root_map and root_map[p]['id']!=v['id']:parents[v['id']]=root_map[p]['id'];break
            rv=all_roots.get(p)
            p=pathnorm(rv.get('parent_path','')).lower() if rv else ''
    pending=sorted(selected,key=lambda v:(v['time'],v['id']));heads={};tips=set();versions=[];source_heads={}
    while pending:
        progress=False
        for v in list(pending):
            pid=parents.get(v['id'])
            if pid and pid not in heads:continue
            parent=heads.get(pid,BASE);name=v['id'].split('__')[-1];refs=[]
            config={k:v['data'][k] for k in ('parameter_overrides','parameters','framework_commit','testcases_commit','framework_revision','compiler_flags','effective_structural_profile','materialized_top_defaults','measured_age_widths') if k in v['data']}
            description=v['data'].get('description') or v['data'].get('implemented_changes',[''])[-1]
            metadata={'version':name,'source_manifest':v['path'],'source_sha256':{p:digest(b) for p,b in sorted(v['source'].items())},'description':description,'configuration':config}
            typ='fix' if re.search(r'fix|repair|legal|width_guard|age_width|dependency_order',name.lower()) else 'perf'
            old=parent;parent=w.commit(BRANCH_VERSIONS,parent,v['source'],typ+'(cpu): '+name.replace('_',' '),v['time'])
            if parent!=old:refs.append(parent)
            source_heads[v['id']]=parent
            if config:
                b=(json.dumps(config,ensure_ascii=False,indent=2)+'\n').encode()
                old=parent;parent=w.commit(BRANCH_VERSIONS,parent,{'history/profiles/'+v['id']+'.json':b},'chore(config): '+name.replace('_',' '),v['time'])
                if parent!=old:refs.append(parent)
            b=(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n').encode()
            old=parent;parent=w.commit(BRANCH_VERSIONS,parent,{'history/versions/'+v['id']+'.json':b},'docs(cpu): '+name.replace('_',' '),v['time'])
            if parent!=old:refs.append(parent)
            heads[v['id']]=parent;tips.discard(heads.get(pid));tips.add(parent)
            versions.append({'version':name,'id':v['id'],'source_manifest':v['path'],'source_sha256':metadata['source_sha256'],'description':description,'parent_version':pid,'source_commit':source_heads[v['id']],'commits':refs})
            pending.remove(v);progress=True
        if not progress:raise RuntimeError('Selected version ancestry cycle')
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    counts=collections.Counter(r['type'] for r in w.records)
    summary={'original_commits':46,'development_versions':len(development),'research_versions':len(versions),'commit_types':dict(counts),'current_implementation':'A109'}
    dump(OUT/'versions.json',versions);dump(OUT/'development.json',development)
    readme='''# Important CPU versions\n\nThis index keeps the original 46 commits, significant development milestones, major architecture changes, candidates measured with the course toolchain, and the final A109 implementation. Small edits for the same version are grouped by source, verification, tooling/configuration, and documentation. Repeated source copies and debug-only changes are consolidated.\n\n- `development.json`: important early milestones and subsequent integrated changes.\n- `versions.json`: selected research versions, source hashes, ancestry, and individual commit links.\n- `summary.json`: repository commit totals and types.\n\nThe `test` commits contain existing verification code and records. This history update runs no CPU simulation, synthesis, or timing evaluation. The current A109 source is preserved.\n'''
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    catalog={p.relative_to(ROOT).as_posix():p.read_bytes() for p in OUT.glob('*')}
    capsule=w.commit(BRANCH_VERSIONS,BASE,catalog,'docs(cpu): index significant research versions',now,merges=sorted(tips))
    final=BASE;groups=collections.defaultdict(dict)
    current_tree=tree(original)
    for p,v in current_tree.items():
        if p.startswith('history/') or p=='tools/reconstruct_research_history_20261006.py':continue
        groups[classify(p)][p]=v
    groups['chore']['tools/curate_important_history.py']=pathlib.Path(__file__).read_bytes()
    t='2026-10-06T03:48:28.047444+00:00'
    for typ in ('source','test','chore','docs'):
        ct='perf' if typ=='source' else typ
        title={'source':'adopt verified ER1 A109 implementation','test':'retain A109 verification coverage and workflows','chore':'retain current course toolchain and project configuration','docs':'retain project design and measured results'}[typ]
        final=w.commit(BRANCH_FINAL,final,groups[typ],ct+'(cpu): '+title,now if typ=='chore' else t)
    final=w.commit(BRANCH_FINAL,final,catalog,'docs(cpu): connect important version history',now,merges=[main_tip,capsule])
    if len(w.records)+47>=1000:raise RuntimeError(f'Important history too large: {len(w.records)+47}')
    w.finish()
    summary['new_commits']=len(w.records)+1;summary['total_commits']=46+summary['new_commits']
    summary['commit_types']=dict(collections.Counter(r['type'] for r in w.records));summary['commit_types']['docs']=summary['commit_types'].get('docs',0)+1
    dump(OUT/'summary.json',summary)
    dump(WORK/'plan.json',{'previous_head':original,'old_refs':oldrefs,'final':final,'main_tip':main_tip,'capsule':capsule,'summary':summary,'records':w.records,'source_heads':source_heads,'selected_ids':[v['id'] for v in selected],'preserved_tree':{p:v for p,v in current_tree.items() if not p.startswith('history/') and p!='tools/reconstruct_research_history_20261006.py'}})
    log(json.dumps(summary,ensure_ascii=False));log('Plan prepared; existing branch references remain unchanged')

def import_selected():
    p=json.loads((WORK/'plan.json').read_text(encoding='utf-8'))
    if git('rev-parse','HEAD').decode().strip()!=p['previous_head']:raise RuntimeError('HEAD changed')
    for branch in (BRANCH_MAIN,BRANCH_VERSIONS,BRANCH_FINAL):
        if subprocess.run(['git','show-ref','--verify','--quiet','refs/heads/'+branch],cwd=ROOT).returncode==0:raise RuntimeError('Selected history branch already exists')
    with (WORK/'important.fastimport').open('rb') as f:
        r=subprocess.run(['git','fast-import','--quiet','--export-marks='+str(WORK/'marks.txt')],cwd=ROOT,stdin=f,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf-8','replace'))
    log('Selected version commits imported; main source unchanged')

def publish():
    p=json.loads((WORK/'plan.json').read_text(encoding='utf-8'));marks={s.split()[0]:s.split()[1] for s in (WORK/'marks.txt').read_text().splitlines()}
    tip=marks[p['final']]
    if git('rev-parse','HEAD').decode().strip()!=p['previous_head']:raise RuntimeError('HEAD changed')
    if git('status','--porcelain=v1','--untracked-files=no').strip():raise RuntimeError('Working files changed')
    def resolve(x):
        if isinstance(x,str):return marks.get(x,x)
        if isinstance(x,list):return [resolve(v) for v in x]
        if isinstance(x,dict):return {k:resolve(v) for k,v in x.items()}
        return x
    for name in ('versions.json','development.json'):
        q=OUT/name;dump(q,resolve(json.loads(q.read_text(encoding='utf-8'))))
    with (INPUT/'enriched_inventory.pickle').open('rb') as f:d=pickle.load(f)
    byid={v['id']:v for v in d['versions']}
    for vid in p['selected_ids']:
        v=byid[vid];actual=tree(marks[p['source_heads'][vid]])
        for name,b in v['source'].items():
            oid=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
            if actual.get(name,(None,None))[1]!=oid:raise RuntimeError('Source snapshot differs: '+vid+' '+name)
    current=tree(tip)
    for name,val in p['preserved_tree'].items():
        if current.get(name)!=tuple(val):raise RuntimeError('Current source differs: '+name)
    # Complete the clickable commit index without changing historic source commits.
    w=Stream(WORK/'index.fastimport');now=dt.datetime.now(dt.timezone.utc).isoformat()
    changes={q.relative_to(ROOT).as_posix():q.read_bytes() for q in OUT.glob('*')}
    w.commit(BRANCH_FINAL,tip,changes,'docs(cpu): complete important version commit index',now);w.finish()
    with (WORK/'index.fastimport').open('rb') as f:
        r=subprocess.run(['git','fast-import','--quiet'],cwd=ROOT,stdin=f,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf-8','replace'))
    final=git('rev-parse','refs/heads/'+BRANCH_FINAL).decode().strip();count=int(git('rev-list','--count',final).decode())
    if count!=p['summary']['total_commits'] or count>=1000:raise RuntimeError('Commit count does not match bounded plan')
    if subprocess.run(['git','merge-base','--is-ancestor',BASE,final],cwd=ROOT).returncode:raise RuntimeError('Original history missing')
    git('update-ref','refs/heads/master',final,p['previous_head'])
    for ref,oid in p['old_refs'].items():git('update-ref','-d',ref,oid)
    git('read-tree',final)
    dump(WORK/'result.json',{'head':final,'total_commits':count,'new_commits':count-46,'important_research_versions':len(p['selected_ids'])})
    log(f'Published {final}; total {count} commits; original 46 commits retained')

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['plan','import','publish']);args=ap.parse_args()
    {'plan':plan,'import':import_selected,'publish':publish}[args.phase]()
