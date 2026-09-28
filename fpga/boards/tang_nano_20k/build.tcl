# Gowin EDA build for Tang Nano 20K (GW2AR-18C). Not run in CI.
#   make bitstream-20k [CORE=synth|mono]   (from the repo root; runs gw_sh in build/gowin/20k-<core>)
# CORE (environment variable AVK_CORE): synth = synth_core with PicoRV32 (default), mono = stage 1.
# or: mkdir -p build/gowin/20k && cd build/gowin/20k && gw_sh <repo>/fpga/boards/tang_nano_20k/build.tcl
# Bitstream: impl/pnr/avk_<core>_20k.fs

set here [file dirname [file normalize [info script]]]
set rtl  [file normalize [file join $here .. .. rtl]]
set core [expr {[info exists ::env(AVK_CORE)] ? $::env(AVK_CORE) : "synth"}]

set_device -name GW2AR-18C GW2AR-LV18QN88C8/I7

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
add_file [file join $here tang_nano_20k_$core.cst]
add_file [file join $here tang_nano_20k.sdc]

set_option -top_module top
set_option -verilog_std sysv2017
set_option -use_mspi_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -output_base_name avk_${core}_20k

run all
