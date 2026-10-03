# Gowin EDA build for Tang Nano 9K (GW1NR-9C). Not run in CI.
#   make bitstream-9k [CORE=synth|mono]   (from the repo root; runs gw_sh in build/gowin/9k-<core>)
# CORE (environment variable AVK_CORE): synth = synth_core with PicoRV32 (default), mono = stage 1.
# or: mkdir -p build/gowin/9k && cd build/gowin/9k && gw_sh <repo>/fpga/boards/tang_nano_9k/build.tcl
# Bitstream: impl/pnr/avk_<core>_9k.fs

set here [file dirname [file normalize [info script]]]
set rtl  [file normalize [file join $here .. .. rtl]]
set core [expr {[info exists ::env(AVK_CORE)] ? $::env(AVK_CORE) : "synth"}]

set_device -name GW1NR-9C GW1NR-LV9QN88PC6/I5

# portable RTL from the shared file list
set fh [open [file join $rtl files.f]]
foreach line [split [read $fh] "\n"] {
    set line [string trim $line]
    if {$line eq "" || [string index $line 0] eq "#"} continue
    add_file [file join $rtl $line]
}
close $fh

# board: vendor wrappers, top, constraints
add_file [file join $here pll_sys.v]
add_file [file join $here top_$core.sv]
add_file [file join $here tang_nano_9k_$core.cst]
add_file [file join $here tang_nano_9k.sdc]

set_option -top_module top
set_option -verilog_std sysv2017
set_option -use_mspi_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -output_base_name avk_${core}_9k

run all
