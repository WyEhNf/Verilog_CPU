"""Record completion of the existing pipeline8 measurement without adopting it."""
from pathlib import Path
import datetime
import json

root = Path('F:/CPU2026Integration/pipeline8_20261003')
path = root/'pipeline8_progress.json'
result = json.loads(path.read_text(encoding='utf-8'))
result['updated_at'] = datetime.datetime.now().astimezone().isoformat()
audit = root/'frequency_priority_audit.json'
if audit.exists():
    measured = json.loads(audit.read_text(encoding='utf-8'))
    result.update(status='PPA_VERIFIED', area=measured['metrics']['area_um2'],
                  frequency='MEASURED', frequency_mhz=measured['frequency_mhz'],
                  ipc=measured['metrics']['ipc'],
                  frequency_target_reached=measured['frequency_target_reached'],
                  stage_goal_achieved=measured['stage_goal_achieved'],
                  full_result=str(root/'verified_cpu_result.json'))
else:
    result.update(status='PPA_INCOMPLETE_INSPECT_LOGS', area='UNVERIFIED',
                  frequency='UNVERIFIED', diagnostic_log=
                  'F:/CPU2026Integration/frequency_priority_20261003/pipeline8_ppa.stderr.log')
path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
