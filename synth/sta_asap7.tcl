# OpenSTA timing check for the flat structural cpu_core netlist.
# Generic memories are explicit black-box timing boundaries; the report must
# therefore be paired with memory_boundaries.json and must not be presented as
# full-chip closure until every boundary has a characterized implementation.
# Usage: sta -no_splash -exit synth/sta_asap7.tcl

if {[info exists ::env(STA_PROJECT_ROOT)]} {
    set root [file normalize $::env(STA_PROJECT_ROOT)]
} else {
    set root [file normalize [file join [file dirname [info script]] ..]]
}
# Use the untouched characterized libraries for timing.  The area flow uses
# normalized filtered copies, but those copies intentionally remove pg_pin
# declarations and therefore generate millions of irrelevant power-pin
# warnings in OpenSTA.
set libdir [file join $root third_party asap7 lib]
set outdir [file join $root build timing p4_i16_d32k_bitmap_fastbb]
file mkdir $outdir
if {[info exists ::env(STA_NETLIST)]} {
    set netlist [file normalize $::env(STA_NETLIST)]
} else {
    set netlist [file join $outdir cpu_core_sta.v]
}
if {[info exists ::env(STA_REPORT)]} {
    set report_file [file normalize $::env(STA_REPORT)]
} else {
    set report_file [file join $outdir timing_300mhz.rpt]
}

foreach lib {
    asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib
    asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib
    asap7sc7p5t_AO_RVT_TT_nldm_201020.lib
    asap7sc7p5t_OA_RVT_TT_nldm_201020.lib
    asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
} {
    read_liberty [file join $libdir $lib]
}

read_verilog $netlist
link_design cpu_core

# ASAP7 Liberty uses ps and fF. Set these explicitly: a bare 3.333 was
# previously interpreted as 3.333 ps, not the intended 3.333 ns.
set_cmd_units -time ps -capacitance fF
set period_ps [expr {1000000.0 / 300.0}]
set path_count 50
if {[info exists ::env(STA_PATH_COUNT)]} {
    set path_count $::env(STA_PATH_COUNT)
    if {![string is integer -strict $path_count] || $path_count < 1} {
        error "STA_PATH_COUNT must be a positive integer"
    }
}
create_clock -name core_clk -period $period_ps [get_ports clk]
set_clock_uncertainty 100.0 [get_clocks core_clk]
# Unspecified input arrival defaults to zero.  Avoid applying an input delay
# to the clock source itself (OpenSTA rejects a delay relative to that clock).
set_output_delay 0.000 -clock core_clk [all_outputs]
set_load 1.0 [all_outputs]

set report_header [open $report_file w]
puts $report_header "AUDIT time_unit=ps capacitance_unit=fF clock_period_ps=$period_ps uncertainty_ps=100 output_load_fF=1"
close $report_header
report_checks -path_delay max -fields {slew cap input_pin} -digits 4 -group_count $path_count >> $report_file
report_worst_slack -digits 4 >> $report_file
report_tns >> $report_file
report_wns >> $report_file
