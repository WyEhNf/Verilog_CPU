"""Record a launched frozen measurement without changing its source manifest."""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime,timezone

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--pid',type=int,required=True)
    args=parser.parse_args()
    p=Path('E:/Verilog_cpu/build/cpu2026/active_frequency_implementation_20261004.json')
    identity=json.loads(p.read_text(encoding='utf-8'))
    manifest=json.loads((args.run/'source_manifest.json').read_text(encoding='utf-8'))
    assert Path(identity['candidate'])==Path(manifest['candidate'])
    assert identity['frozen_manifest_sha256']==sha(args.run/'source_manifest.json')
    for n,h in identity['source_sha256'].items():
        assert sha(Path('E:/Verilog_cpu')/n)==h,n
    identity.update(tests_started=True,status='WORKTREE_IMPLEMENTED_MEASUREMENT_IN_PROGRESS',
                    measurement_process_id=args.pid,measurement_started_at=datetime.now(timezone.utc).isoformat())
    p.write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=identity['status'],run=str(args.run),pid=args.pid)))

if __name__=='__main__':
    main()
