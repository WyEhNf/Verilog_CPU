# Timing characterization of an already ASAP7-mapped netlist using Yosys'
# built-in static timing pass. Memory cells remain timing boundaries.

yosys -import
set root [file normalize [file join [file dirname [info script]] ..]]
set libdir [file join $root _asap7_lib_filtered]
set indir [file join $root build synth p4_i16_d32k_bitmap_fastbb_bb]
set outdir [file join $root build timing p4_i16_d32k_bitmap_fastbb]
file mkdir $outdir

read_verilog [file join $indir cpu_core_synth.v]
foreach lib {
    asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib
    asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib
    asap7sc7p5t_AO_RVT_TT_nldm_201020.lib
    asap7sc7p5t_OA_RVT_TT_nldm_201020.lib
    asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
} {
    read_liberty -wb -ignore_miss_func [file join $libdir $lib]
}
hierarchy -check -top cpu_core
yosys proc
memory_dff
memory_collect
flatten
opt_clean
tee -o [file join $outdir xnor_cells.il] dump t:XNOR2xp5_ASAP7_75t_R
tee -o [file join $outdir longest_logic_path.log] ltp -noff
tee -o [file join $outdir yosys_sta.log] sta
