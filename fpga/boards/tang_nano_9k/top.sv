// Tang Nano 9K top, stage 0: stub_core (sine/saw -> I2S, MIDI echo, blink).
// LEDs (active low): 0 blink 1 Hz, 1 toggles per MIDI byte, 2 PLL locked, 3 DAC unmuted.
`default_nettype none

module top (
    input  wire       clk_27m,
    input  wire       btn_rst_n,  // S1, active low
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
    wire        arst = ~pll_lock | ~btn_rst_n;
    logic [3:0] rst_sr;
    wire        rst  = rst_sr[3];

    always_ff @(posedge clk or posedge arst) begin
        if (arst) rst_sr <= '1;
        else      rst_sr <= {rst_sr[2:0], 1'b0};
    end

    logic       led_blink, led_midi;
    logic [7:0] midi_data;
    logic       midi_valid;

    stub_core #(
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
        .midi_data (midi_data),
        .midi_valid(midi_valid)
    );

    assign led_n = ~{2'b00, dac_xsmt, pll_lock, led_midi, led_blink};

    wire unused = &{1'b0, midi_data, midi_valid};

endmodule

`default_nettype wire
