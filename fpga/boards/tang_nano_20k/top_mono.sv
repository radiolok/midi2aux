// Tang Nano 20K top: mono_core (stage 1, no CPU). Select with CORE=mono.
// Stage 1: mono_core (MIDI -> one square voice, gate CV on OUT2).
// LEDs (active low): 0 blink 1 Hz, 1 toggles per MIDI event, 2 gate, 3 PLL locked, 4 DAC unmuted.
`default_nettype none

module top (
    input  wire       clk_27m,
    input  wire       btn_rst,    // S1, active high
    input  wire       midi_rx,    // after the optocoupler, idle high
    output wire       i2s_bck,
    output wire       i2s_lrck,
    output wire       i2s_din,
    output wire       dac_xsmt,
    output wire [5:0] led_n
);

    localparam int SYS_CLK_HZ = 99_000_000;  // see pll_sys.v

    wire clk, pll_lock;

    pll_sys u_pll (
        .clkin (clk_27m),
        .clkout(clk),
        .lock  (pll_lock)
    );

    // reset: asserted asynchronously, released synchronously
    wire        arst = ~pll_lock | btn_rst;
    logic [3:0] rst_sr;
    wire        rst  = rst_sr[3];

    always_ff @(posedge clk or posedge arst) begin
        if (arst) rst_sr <= '1;
        else      rst_sr <= {rst_sr[2:0], 1'b0};
    end

    logic led_blink, led_midi, led_gate;

    mono_core #(
        .SYS_CLK_HZ(SYS_CLK_HZ)
    ) u_core (
        .clk       (clk),
        .rst       (rst),
        .midi_rx   (midi_rx),
        .i2s_bck   (i2s_bck),
        .i2s_lrck  (i2s_lrck),
        .i2s_din   (i2s_din),
        .dac_xsmt  (dac_xsmt),
        .led_blink (led_blink),
        .led_midi  (led_midi),
        .led_gate  (led_gate)
    );

    assign led_n = ~{1'b0, dac_xsmt, pll_lock, led_gate, led_midi, led_blink};

endmodule

`default_nettype wire
