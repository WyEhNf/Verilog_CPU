# ASAP7 area synthesis flow for cpu_core (Yosys) -- SRAM-blackbox variant.
#
# Cache/predictor arrays stay as unmapped $mem cells (memory -nomap), so the
# stat -liberty area below covers logic + flops only.  The missing piece for
# the plan.md ENV-04 main metric is the ASAP7 SRAM macro area for those
# arrays must be added only after a legal SRAM implementation is assigned.
# Closest-size macro pricing alone does not account for ports/adapters and
# cannot establish the required FakeRAM total. Register-based upper bound:
# synth.tcl.
#
# Usage: yosys -p "tcl synth/synth_bb.tcl <fe> <be> <phys_regs> <rob_entries> <outdir>"

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
set dcache_index_hash [lindex $argv 24]
set dcache_request_pipeline [lindex $argv 25]
set dcache_ways [lindex $argv 26]
set ram_size_bytes [lindex $argv 27]
set legacy_sentinel_halt [lindex $argv 28]
set icache_lines [lindex $argv 29]
set icache_ways [lindex $argv 30]
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
if {$dcache_index_hash eq ""} { set dcache_index_hash 0 }
if {$dcache_request_pipeline eq ""} { set dcache_request_pipeline 0 }
if {$dcache_ways eq ""} { set dcache_ways 1 }
if {$ram_size_bytes eq ""} { set ram_size_bytes 268435456 }
if {$legacy_sentinel_halt eq ""} { set legacy_sentinel_halt 0 }
if {$icache_lines eq ""} { set icache_lines 64 }
if {$icache_ways eq ""} { set icache_ways 2 }
set libdir      "_asap7_lib_filtered"

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
        -set DCACHE_REQUEST_PIPELINE $dcache_request_pipeline \
        -set DCACHE_WAYS $dcache_ways -set RAM_SIZE_BYTES $ram_size_bytes \
        -set LEGACY_SENTINEL_HALT $legacy_sentinel_halt \
        -set ICACHE_LINES $icache_lines -set ICACHE_WAYS $icache_ways cpu_core
hierarchy -check -top cpu_core
procs
opt
fsm
opt
# The generic `memory -nomap` pipeline runs opt_mem_priority over every
# multi-write-port ROB/RS/LSQ array.  That pass is quadratic in the generated
# write ports and does not change the priced result here because the memories
# deliberately remain unpriced black boxes.  Merge adjacent registers where
# possible, then collect the exact geometry/ports without rewriting priority.
memory_dff
memory_collect
# Opt-in cache-port consolidation. The generic memory_share pass is restricted
# to cache data/tag arrays; ROB/RS/LSQ multi-write arrays remain untouched.
# Same-address mutually exclusive refill ports may share one physical port,
# but simultaneous store-hit/refill accesses still need separate data writes.
if {[info exists ::env(ASAP7_CACHE_MEMORY_SHARE)]} {
    if {$::env(ASAP7_CACHE_MEMORY_SHARE) ni {0 1}} {
        error "ASAP7_CACHE_MEMORY_SHARE must be 0 or 1"
    }
    if {$::env(ASAP7_CACHE_MEMORY_SHARE) eq "1"} {
        tee -o $outdir/memory_manifest_before_share.il dump {t:$mem*}
        memory_share */data_mem */tag_mem
        opt_clean
    }
}
# Preserve the memory geometry and port counts before technology mapping.  The
# post-run audit treats every one of these cells as unpriced until an SRAM,
# banked/replicated macro implementation, or explicit standard-cell mapping is
# assigned.
tee -o $outdir/memory_manifest.il dump {t:$mem*}
techmap
opt
# Legalize flops before the final combinational mapping.  The usable ASAP7
# positive-edge cell exposes QN, so dfflibmap introduces polarity/input-select
# logic.  Mapping flops after ABC left that logic as unpriced $_NOT_/$_MUX_.
dfflibmap -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
opt
# ABC's bundled liberty->genlib conversion cannot ingest ASAP7 NLDM libs
# (&nf crashes, map/if see "only 2 cell classes").  Use a generated SIS genlib
# + classic `map` for all remaining combinational logic.
# genlib generated by tools/liberty2genlib.py; area cost is scaled x10000 there
# and stat -liberty below reads the LEF-normalized filtered liberty files.
set abc_map_script "+strash;scorr;dc2;dretime;strash;map -a"
# ASAP7_ABC_DELAY_MAP=1 keeps the same RTL/netlist flow but asks ABC to
# minimize mapped logic depth instead of area. Keep area-only as the default
# so existing audits remain reproducible and the timing trade-off is explicit.
if {[info exists ::env(ASAP7_ABC_DELAY_MAP)] && $::env(ASAP7_ABC_DELAY_MAP) eq "1"} {
    set abc_map_script "+strash;scorr;dc2;dretime;strash;map"
}
abc -genlib _asap7_lib_filtered/asap7_comb.genlib -script $abc_map_script
opt

tee -o $outdir/synth.log stat -liberty $libdir/asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_AO_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_OA_RVT_TT_nldm_201020.lib \
    -liberty $libdir/asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
write_verilog -noattr $outdir/cpu_core_synth.v
tee -o $outdir/stat_after_abc.log stat
