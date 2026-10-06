"""Summarize measured screening paths; do not infer correctness or IPC."""
from pathlib import Path
import argparse,hashlib,json

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory',type=Path);a=ap.parse_args()
    root=a.directory
    screen=json.loads((root/'screening.json').read_text(encoding='utf-8'))
    paths=json.loads((root/'critical_paths.json').read_text(encoding='utf-8'))['checks']
    result=dict(status='MEASURED_UNVALIDATED_CANDIDATE',screening=screen,
        critical_paths_sha256=sha(root/'critical_paths.json'),paths=[])
    for path in paths:
        points=path['source_path'];gates=[]
        for index,p in enumerate(points):
            if index and p.get('capacitance') is not None:
                gates.append(dict(pin=p['pin'],cell=p['cell'],
                    delay_ns=(p['arrival']-points[index-1]['arrival'])*1e9,
                    load_ff=p['capacitance']*1e15,slew_ns=p.get('slew',0)*1e9))
        gates.sort(key=lambda p:p['delay_ns'],reverse=True)
        result['paths'].append(dict(startpoint=path['startpoint'],endpoint=path['endpoint'],
            arrival_ns=points[-1]['arrival']*1e9,combinational_cells=len(gates),slowest_gates=gates[:6]))
    dest=root/'screen_path_summary.json';dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
