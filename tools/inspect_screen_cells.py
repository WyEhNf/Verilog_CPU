"""Read exact physical cell ports from the timed Verilog without re-exporting."""
from pathlib import Path
import argparse,hashlib,json,re

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory',type=Path)
    ap.add_argument('--cell',action='append',required=True);a=ap.parse_args()
    root=a.directory;area=json.loads((root/'area_audit.json').read_text(encoding='utf-8'))
    net=root/'mapped.v'
    with net.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==area['netlist_sha256']
    wanted=set(a.cell);found={};scope=None;current=None
    with net.open(encoding='utf-8') as f:
        for line in f:
            m=re.match(r'^module\s+([^\s(]+)',line)
            if m:scope=m[1].lstrip('\\')
            if scope!='student_top':continue
            m=re.match(r'^  (\S+)\s+(\S+)\s+\($',line)
            if m and m[2] in wanted:
                current=dict(cell=m[2],type=m[1],ports={});assert m[2] not in found
                found[m[2]]=current
            elif current:
                m=re.match(r'\s+\.(\w+)\((.*?)\)\s*[,;]?\s*$',line)
                if m:current['ports'][m[1]]=m[2].strip()
                elif line.strip()==');':current=None
    assert found.keys()==wanted
    print(json.dumps(dict(netlist_sha256=area['netlist_sha256'],cells=found),indent=2))

if __name__=='__main__':main()
