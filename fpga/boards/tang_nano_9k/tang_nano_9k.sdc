// 27 MHz board oscillator; the PLL output clock (99 MHz) is derived by the tool.
create_clock -name clk_27m -period 37.037 -waveform {0 18.518} [get_ports {clk_27m}]
