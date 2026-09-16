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
set mul_impl    [lindex $argv 8]
set enable_caches [lindex $argv 9]
set enable_predictor [lindex $argv 10]
if {$rs_entries eq ""}  { set rs_entries 8 }
if {$lsq_entries eq ""} { set lsq_entries 8 }
if {$cache_stats eq ""} { set cache_stats 0 }
if {$mul_impl eq ""}    { set mul_impl 0 }
if {$enable_caches eq ""} { set enable_caches 1 }
if {$enable_predictor eq ""} { set enable_predictor 1 }
set libdir      "_asap7_lib_filtered"

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
        -set ENABLE_CACHE_STATS $cache_stats -set MUL_IMPL $mul_impl \
        -set ENABLE_CACHES $enable_caches \
        -set ENABLE_PREDICTOR $enable_predictor cpu_core
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
# `map` (see synth_bb.tcl / tools/liberty2genlib.py).  Legalize flops before
# ABC so the polarity logic introduced by dfflibmap is also technology mapped.
dfflibmap -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
opt
abc -genlib _asap7_lib_filtered/asap7_comb.genlib \
    -script "+strash;scorr;dc2;dretime;strash;map"
opt

tee -o $outdir/synth.log stat -liberty $libdir/asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_AO_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_OA_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
write_verilog -noattr $outdir/cpu_core_synth.v
tee -o $outdir/stat_after_abc.log stat
