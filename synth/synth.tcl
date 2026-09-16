# ASAP7 area synthesis flow for cpu_core (Yosys) -- register-based variant.
#
# Every array is explicitly mapped to logic after memory_dff.  memory_dff by
# itself only merges surrounding flops into memories; it does not provide the
# register-based reference promised by plan.md ENV-04.
# The SRAM-blackbox metric is synth_bb.tcl; the two numbers must be reported
# separately.
#
# Usage: yosys -p "tcl synth/synth.tcl <fe> <be> <phys_regs> <rob_entries> <outdir>"
#   e.g. yosys -p "tcl synth/synth.tcl 1 1 64 32 build/synth/fe1_be1_p64_r32"
#
# Library: ASAP7 7.5T RVT TT NLDM standard cells, fixed to the files under
# third_party/asap7/lib (plan.md ENV-04).  LVT/SLVT mixing and FF/SS corners
# are intentionally out of scope for the area metric.
#
# The same script, library files and constraints must be used for every
# configuration so the area numbers stay comparable.

yosys -import

set fe_width    [lindex $argv 0]
set be_width    [lindex $argv 1]
set phys_regs   [lindex $argv 2]
set rob_entries [lindex $argv 3]
set outdir      [lindex $argv 4]
set rs_entries  [lindex $argv 5]
set lsq_entries [lindex $argv 6]
set cache_stats [lindex $argv 7]
if {$rs_entries eq ""}  { set rs_entries 8 }
if {$lsq_entries eq ""} { set lsq_entries 8 }
if {$cache_stats eq ""} { set cache_stats 0 }
set libdir      "third_party/asap7/lib"

file mkdir $outdir

# Single source of truth for the RTL file list: rtl/filelist.f.
set f [open "rtl/filelist.f" r]
set rtl_files {}
while {[gets $f line] >= 0} {
    if {[string trim $line] ne ""} { lappend rtl_files [string trim $line] }
}
close $f

read_verilog -I rtl {*}$rtl_files
chparam -set FE_WIDTH $fe_width -set BE_WIDTH $be_width \
        -set PHYS_REGS $phys_regs -set ROB_ENTRIES $rob_entries \
        -set RS_ENTRIES $rs_entries -set LSQ_ENTRIES $lsq_entries \
        -set ENABLE_CACHE_STATS $cache_stats cpu_core
hierarchy -check -top cpu_core
procs
opt
fsm
opt
memory_dff
# Record the original memory shapes before the deliberately expensive
# register/mux expansion used by the A_ff_reference profile.
tee -o $outdir/memory_manifest.il dump {t:$mem*}
memory_map
techmap
opt
# ABC's bundled liberty->genlib conversion cannot ingest ASAP7 NLDM libs
# (&nf crashes).  Map combinational logic via a generated SIS genlib + classic
# `map`, then map the flops with dfflibmap (see synth_bb.tcl / tools/liberty2genlib.py).
abc -genlib _asap7_lib_filtered/asap7_comb.genlib \
    -script "+strash;scorr;dc2;dretime;strash;map"
dfflibmap -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
opt

tee -o $outdir/synth.log stat -liberty $libdir/asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_AO_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_OA_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
write_verilog -noattr $outdir/cpu_core_synth.v
tee -o $outdir/stat_after_abc.log stat
