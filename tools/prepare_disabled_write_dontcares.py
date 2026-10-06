"""Express unused field write-data as don't-care; enabled writes stay defined."""
from pathlib import Path
import hashlib,json,re,shutil

BASE=Path('F:/CPU2026Candidates/local_alu_fields_v10_20261003')
STAGE=Path('F:/CPU2026Candidates/local_transactions_v11_20261003')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    assert not STAGE.exists(),'Preserve previous candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for n,h in manifest['source_sha256'].items():
        assert sha(BASE/n)==h.lower(),n
        p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/n,p)
    for name,expected in [('rtl/backend/rv32_lsq.v',25),('rtl/backend/rv32_reservation_station.v',15)]:
        p=STAGE/name;text=p.read_text(encoding='utf-8')
        # Each enabled command still assigns the complete field exactly where
        # the original clocked block assigned it. The state bank holds its FFs
        # when write_enable=0, independent of data_i. No architectural value,
        # valid bit, completion payload, SRAM content or accepted write is X'd.
        pattern=r'(\b\w+_mem_write_data\[bank_default_row\])=0;'
        text,n=re.subn(pattern,r"\1='x;",text);assert n==expected,(name,n)
        assert not re.search(r'\w+_mem_write_data\[[^;\n]+\]\[[^;\n]+\]\s*=',text),'Partial enabled field assignment'
        p.write_text(text,encoding='utf-8')
        manifest['changed'].append(dict(file=name,change='Disabled write-data is unconstrained; write enables and all enabled field updates unchanged'))
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},tool_sha256=sha(__file__),
        strategy=manifest['strategy']+'; remove meaningless inactive field-data masks while retaining exact enabled-write priority')
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True)))

if __name__=='__main__':main()
