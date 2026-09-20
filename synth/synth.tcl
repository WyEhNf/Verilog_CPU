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
set fetch_queue_depth [lindex $argv 11]
set completion_depth [lindex $argv 12]
set shift_impl [lindex $argv 13]
set phys_tag_impl [lindex $argv 14]
set generation_width [lindex $argv 15]
set checkpoint_impl [lindex $argv 16]
set completion_bypass [lindex $argv 17]
set serial_backend [lindex $argv 18]
set int_issue_width [lindex $argv 19]
set cdb_width [lindex $argv 20]
set icache_mshrs [lindex $argv 21]
set dcache_mshrs [lindex $argv 22]
set dcache_lines [lindex $argv 23]
if {$rs_entries eq ""}  { set rs_entries 8 }
if {$lsq_entries eq ""} { set lsq_entries 8 }
if {$cache_stats eq ""} { set cache_stats 0 }
if {$mul_impl eq ""}    { set mul_impl 0 }
if {$enable_caches eq ""} { set enable_caches 1 }
if {$enable_predictor eq ""} { set enable_predictor 1 }
if {$fetch_queue_depth eq ""} { set fetch_queue_depth 16 }
if {$completion_depth eq ""} { set completion_depth 4 }
if {$shift_impl eq ""} { set shift_impl 0 }
if {$phys_tag_impl eq ""} { set phys_tag_impl 0 }
if {$generation_width eq ""} { set generation_width 8 }
if {$checkpoint_impl eq ""} { set checkpoint_impl 0 }
if {$completion_bypass eq ""} { set completion_bypass 0 }
if {$serial_backend eq ""} { set serial_backend 0 }
if {$int_issue_width eq ""} { set int_issue_width [expr {$be_width < 2 ? $be_width : 2}] }
if {$cdb_width eq ""} { set cdb_width [expr {$be_width < 2 ? $be_width : 2}] }
if {$icache_mshrs eq ""} { set icache_mshrs 8 }
if {$dcache_mshrs eq ""} { set dcache_mshrs 4 }
if {$dcache_lines eq ""} { set dcache_lines 256 }
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
        -set ENABLE_PREDICTOR $enable_predictor \
        -set FETCH_QUEUE_DEPTH $fetch_queue_depth \
        -set COMPLETION_DEPTH $completion_depth \
        -set SHIFT_IMPL $shift_impl \
        -set PHYS_TAG_IMPL $phys_tag_impl \
        -set GENERATION_WIDTH $generation_width \
        -set CHECKPOINT_IMPL $checkpoint_impl cpu_core
chparam -set COMPLETION_BYPASS $completion_bypass cpu_core
chparam -set SERIAL_BACKEND $serial_backend cpu_core
chparam -set INT_ISSUE_WIDTH $int_issue_width -set CDB_WIDTH $cdb_width cpu_core
chparam -set ICACHE_MSHRS $icache_mshrs -set DCACHE_MSHRS $dcache_mshrs \
        -set DCACHE_LINES $dcache_lines cpu_core
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
    -script "+strash;scorr;dc2;dretime;strash;map -a"
opt

tee -o $outdir/synth.log stat -liberty $libdir/asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_AO_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_OA_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
write_verilog -noattr $outdir/cpu_core_synth.v
tee -o $outdir/stat_after_abc.log stat
