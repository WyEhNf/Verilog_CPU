"""Read-only STA-to-RTL identity audit with the complete nested physical census."""
from pathlib import Path
import json
import sys
import audit_full_timing_identity as identity
import verify_course_axi_area_nested as nested
from verify_course_axi_area import sha256


if __name__ == '__main__':
    index=sys.argv.index('--outdir')
    out=Path(sys.argv[index+1]).resolve()
    hashes={str(Path(p).resolve()):sha256(p) for p in (__file__,identity.__file__,nested.__file__)}
    identity.verify=nested.verify
    identity.expand_stat_census=nested.expand_stat_census
    identity.main()
    p=out/'identity.json';r=json.loads(p.read_text())
    for name,h in hashes.items():assert sha256(name)==h,name
    r['input_sha256'].update(hashes)
    r['nested_census_adapter']=str(Path(__file__).resolve())
    p.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
