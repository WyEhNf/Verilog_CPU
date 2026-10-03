"""Read-only endpoint timing inventory for the adopted combined CPU."""
from pathlib import Path
import json
import subprocess
import hashlib

AREA = Path('F:/CPU2026Integration/frequency_combined_v2_20261003/area')
OUT = Path('F:/CPU2026Proofs/frequency_combined_paths_20261003')
STA = '/mnt/f/CPU2026Candidates/frequency_combined_v2_20261003/.deps/OpenSTA/build/sta'

def linux(p):
    p = Path(p).resolve().as_posix()
    return '/mnt/' + p[0].lower() + p[2:]

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def setup():
    s = (AREA/'full_timing.tcl').read_text()
    s = s[:s.index('\nsource ')]
    return s + '\nread_sdc "' + linux(AREA/'constraints.sdc') + '"\n'

def run(name, body):
    OUT.mkdir(exist_ok=True, parents=True)
    script = OUT/(name+'.tcl')
    assert not script.exists(), 'Preserve previous diagnostic'
    script.write_text(setup()+body+'\n} message]} {puts stderr $message; exit 1}\nexit 0\n', encoding='utf-8')
    with (OUT/(name+'.log')).open('w', encoding='utf-8') as f:
        subprocess.run(['wsl.exe','--exec',STA,'-no_init','-exit',linux(script)], stdout=f, stderr=subprocess.STDOUT,check=True)

if __name__ == '__main__':
    inputs = {str(AREA/n):sha(AREA/n) for n in ['mapped.v','constraints.sdc','full_timing.tcl']}
    assert inputs[str(AREA/'mapped.v')] == '1e6f1129049b161208cb61fd5432f0f00b55d2127e77c64e40a8d3c0893b2538'
    d = linux(OUT)
    run('inventory', '''
if {![check_setup -verbose > "''' + d + '''/setup_checks.rpt"]} {error "Incomplete constraints"}
set paths [find_timing_paths -path_delay max -group_path_count 1000000 -endpoint_path_count 1 -sort_by_slack]
set f [open "''' + d + '''/endpoint_paths.tsv" w]
puts $f "startpoint\tendpoint\tarrival_ns\trequired_ns\tslack_ns"
foreach path $paths {
  set start [get_full_name [get_property $path startpoint]]
  set end [get_full_name [get_property $path endpoint]]
  puts $f [join [list $start $end [expr {[$path data_arrival_time]*1e9}] [expr {[$path data_required_time]*1e9}] [expr {[$path slack]*1e9}]] "\t"]
}
close $f
puts "INVENTORY_PATHS [llength $paths]"
report_checks -path_delay max -group_path_count 200 -endpoint_path_count 1 -sort_by_slack -format json > "''' + d + '''/top200.json"
report_checks -path_delay max -group_path_count 20 -sort_by_slack -format full_clock -fields {slew capacitance fanout input_pins} -digits 6 > "''' + d + '''/top20.rpt"
''')
    for p,h in inputs.items(): assert sha(p)==h, p
    (OUT/'inventory_inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    print((OUT/'inventory.log').read_text()[-5000:])
