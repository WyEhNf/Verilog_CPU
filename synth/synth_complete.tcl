# ASAP7 complete-area audit flow for cpu_core.
#
# The two cache data arrays are the only memories retained as SRAM macro
# boundaries.  Every tag, predictor, queue, PRF, ROB, RS, LSQ and MSHR array
# is expanded to ASAP7 standard cells.  The companion audit script adds the
# characterized ASAP7 SRAM macro area for the two retained arrays.
#
# Usage matches synth.tcl:
#   yosys -p "tcl synth/synth_complete.tcl <parameters...>"

yosys -import

set fe_width              [lindex $argv 0]
set be_width              [lindex $argv 1]
set phys_regs             [lindex $argv 2]
set rob_entries           [lindex $argv 3]
set outdir                [lindex $argv 4]
set rs_entries            [lindex $argv 5]
set lsq_entries           [lindex $argv 6]
set cache_stats           [lindex $argv 7]
set mul_impl              [lindex $argv 8]
set enable_caches         [lindex $argv 9]
set enable_predictor      [lindex $argv 10]
set fetch_queue_depth     [lindex $argv 11]
set completion_depth      [lindex $argv 12]
set shift_impl            [lindex $argv 13]
set phys_tag_impl         [lindex $argv 14]
set generation_width      [lindex $argv 15]
set checkpoint_impl       [lindex $argv 16]
set completion_bypass     [lindex $argv 17]
set serial_backend        [lindex $argv 18]
set int_issue_width       [lindex $argv 19]
set cdb_width             [lindex $argv 20]
set icache_mshrs          [lindex $argv 21]
set dcache_mshrs          [lindex $argv 22]
set dcache_lines          [lindex $argv 23]
set dcache_index_hash     [lindex $argv 24]
set dcache_request_pipeline [lindex $argv 25]

if {$rs_entries eq ""}          { set rs_entries 8 }
if {$lsq_entries eq ""}         { set lsq_entries 8 }
if {$cache_stats eq ""}         { set cache_stats 0 }
if {$mul_impl eq ""}            { set mul_impl 0 }
if {$enable_caches eq ""}       { set enable_caches 1 }
if {$enable_predictor eq ""}    { set enable_predictor 1 }
if {$fetch_queue_depth eq ""}   { set fetch_queue_depth 16 }
if {$completion_depth eq ""}    { set completion_depth 4 }
if {$shift_impl eq ""}          { set shift_impl 0 }
if {$phys_tag_impl eq ""}       { set phys_tag_impl 0 }
if {$generation_width eq ""}    { set generation_width 8 }
if {$checkpoint_impl eq ""}     { set checkpoint_impl 0 }
if {$completion_bypass eq ""}   { set completion_bypass 0 }
if {$serial_backend eq ""}      { set serial_backend 0 }
if {$int_issue_width eq ""}     { set int_issue_width [expr {$be_width < 2 ? $be_width : 2}] }
if {$cdb_width eq ""}           { set cdb_width [expr {$be_width < 2 ? $be_width : 2}] }
if {$icache_mshrs eq ""}        { set icache_mshrs 8 }
if {$dcache_mshrs eq ""}        { set dcache_mshrs 4 }
if {$dcache_lines eq ""}        { set dcache_lines 256 }
if {$dcache_index_hash eq ""}   { set dcache_index_hash 0 }
if {$dcache_request_pipeline eq ""} { set dcache_request_pipeline 0 }

set libdir "_asap7_lib_filtered"
file mkdir $outdir

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
        -set DCACHE_LINES $dcache_lines -set DCACHE_INDEX_HASH $dcache_index_hash \
        -set DCACHE_REQUEST_PIPELINE $dcache_request_pipeline cpu_core

hierarchy -check -top cpu_core
procs
opt
fsm
opt
memory_dff
memory_collect

# Preserve only the two cache line-data arrays.  They are synchronous-read
# candidates and can be implemented by the characterized ASAP7 6T macros.
# Cache tags and every multi-ported control structure are deliberately mapped
# to standard cells so their cost is not hidden behind an invalid 1-port SRAM.
setattr -set audit_sram 1 *rv32_icache_nonblocking/data_mem
setattr -set audit_sram 1 *rv32_dcache_nonblocking/data_mem
tee -o $outdir/memory_manifest.il dump {t:$mem*}
memory_map -attr !audit_sram
tee -o $outdir/retained_sram_manifest.il dump {t:$mem*}

techmap
opt
dfflibmap -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
opt
abc -genlib $libdir/asap7_comb.genlib \
    -script "+strash;scorr;dc2;dretime;strash;map -a"
opt

tee -o $outdir/synth.log stat \
    -liberty $libdir/asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_AO_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_OA_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
write_verilog -noattr $outdir/cpu_core_synth.v
tee -o $outdir/stat_after_abc.log stat
