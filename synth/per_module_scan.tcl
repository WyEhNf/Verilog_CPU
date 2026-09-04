# Per-module procs timing.  Reads each file in rtl/filelist.f alone, runs
# procs, prints wall time per module.  Identifies the module(s) that make
# the full-design procs pathologically slow.  Diagnostics only.
yosys -import

set f [open "rtl/filelist.f" r]
set files {}
while {[gets $f line] >= 0} {
    if {[string trim $line] ne ""} { lappend files [string trim $line] }
}
close $f

foreach path $files {
    set t0 [clock milliseconds]
    set rc [catch {read_verilog -I rtl $path} err]
    if {$rc} {
        puts "MODULE [file tail $path] read_error $err"
        design -reset
        continue
    }
    set rc [catch {procs} err]
    set dt [expr {[clock milliseconds] - $t0}]
    if {$rc} {
        puts "MODULE [file tail $path] procs_ms=$dt PROC_ERROR $err"
    } else {
        puts "MODULE [file tail $path] procs_ms=$dt ok"
    }
    design -reset
}
