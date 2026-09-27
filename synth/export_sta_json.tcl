# Export the mapped logic as a flat, structural Yosys JSON netlist.
# Generic memories remain explicit $mem_v2 cells so the companion converter
# can replace them with named timing boundaries instead of behavioral Verilog.

yosys -import
set root [file normalize [file join [file dirname [info script]] ..]]
set libdir [file join $root _asap7_lib_filtered]
# Optional directories let the same flow audit the current candidate instead
# of silently exporting the historical P4/D32K snapshot.
set indir [lindex $argv 0]
set outdir [lindex $argv 1]
if {$indir eq ""} { set indir [file join $root build synth p4_i16_d32k_bitmap_fastbb_bb] }
if {$outdir eq ""} { set outdir [file join $root build timing p4_i16_d32k_bitmap_fastbb] }
set indir [file normalize $indir]
set outdir [file normalize $outdir]
file mkdir $outdir

foreach lib {
    asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib
    asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib
    asap7sc7p5t_AO_RVT_TT_nldm_201020.lib
    asap7sc7p5t_OA_RVT_TT_nldm_201020.lib
    asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
} {
    read_liberty -lib -ignore_miss_func [file join $libdir $lib]
}

set direct_mapped [file exists [file join $indir cpu_core_mapped.il]]
if {$direct_mapped} {
    puts "STA input_mode=exact_mapped_rtlil"
    read_rtlil [file join $indir cpu_core_mapped.il]
} else {
    puts "STA input_mode=behavioral_verilog_compatibility"
    read_verilog [file join $indir cpu_core_synth.v]
}
hierarchy -check -top cpu_core
if {!$direct_mapped} {
yosys proc
memory_dff
memory_collect
}
flatten
opt_clean
# Re-reading Yosys' behavioral memory emission recreates generic priority and
# port-selection logic around $mem_v2.  Map that glue back to ASAP7 cells so
# the exported STA netlist contains no uncharacterized combinational cells.
if {!$direct_mapped} {
techmap
opt
dfflibmap -liberty [file join $libdir asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib]
opt
abc -genlib [file join $libdir asap7_comb.genlib] \
    -script "+strash;scorr;dc2;dretime;strash;map -a"
opt
}
tee -o [file join $outdir sta_logic_area.log] stat \
    -liberty [file join $libdir asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib] \
    -liberty [file join $libdir asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib] \
    -liberty [file join $libdir asap7sc7p5t_AO_RVT_TT_nldm_201020.lib] \
    -liberty [file join $libdir asap7sc7p5t_OA_RVT_TT_nldm_201020.lib] \
    -liberty [file join $libdir asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib]
select cpu_core
write_json -selected -noscopeinfo [file join $outdir cpu_core_flat.json]
