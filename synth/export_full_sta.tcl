# Export an already fully mapped area netlist without memory black boxes.
# Usage: yosys -p "tcl synth/export_full_sta.tcl <synthesis_dir> <timing_dir>"
yosys -import
set indir [lindex $argv 0]
set outdir [lindex $argv 1]
file mkdir $outdir
foreach lib [glob _asap7_lib_filtered/*.lib] {
    read_liberty -lib -ignore_miss_func $lib
}
read_verilog $indir/cpu_core_synth.v
hierarchy -check -top cpu_core
flatten
opt_clean
select -assert-none {t:$*} {t:$scopeinfo} %d
select cpu_core
write_json -selected -noscopeinfo $outdir/cpu_core_flat.json
