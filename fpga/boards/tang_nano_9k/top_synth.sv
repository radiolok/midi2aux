// Tang Nano 9K top: synth_core (PicoRV32 SoC + audio). Select with CORE=synth (default).
// LEDs (active low): 0..3 firmware GPIO, 4 MIDI activity, 5 CPU trap.
`default_nettype none

module top (
    input  wire       clk_27m,
    input  wire       btn_rst_n,  // S1, active low
    input  wire       btn_user_n, // S2, active low
    input  wire       midi_rx,    // after the optocoupler, idle high
    input  wire       uart_rx,    // BL702 USB-UART
    output wire       uart_tx,
    output wire       flash_sck,
    output wire       flash_mosi,
    input  wire       flash_miso,
    output wire       flash_cs_n,
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

    wire        arst = ~pll_lock | ~btn_rst_n;
    logic [3:0] rst_sr;
    wire        rst  = rst_sr[3];

    always_ff @(posedge clk or posedge arst) begin
        if (arst) rst_sr <= '1;
        else      rst_sr <= {rst_sr[2:0], 1'b0};
    end

    logic [5:0] led;
    logic       trap;

    synth_core #(
        .SYS_CLK_HZ     (SYS_CLK_HZ),
        .RAM_BYTES      (32768),
        .FW_FLASH_OFFSET(32'h0010_0000)
    ) u_core (
        .clk       (clk),
        .rst       (rst),
        .midi_rx   (midi_rx),
        .uart_rx   (uart_rx),
        .uart_tx   (uart_tx),
        .flash_sck (flash_sck),
        .flash_mosi(flash_mosi),
        .flash_miso(flash_miso),
        .flash_cs_n(flash_cs_n),
        .i2s_bck   (i2s_bck),
        .i2s_lrck  (i2s_lrck),
        .i2s_din   (i2s_din),
        .dac_xsmt  (dac_xsmt),
        .led       (led),
        .btn       ({1'b0, ~btn_user_n}),
        .trap      (trap)
    );

    assign led_n = ~led;

    wire unused = &{1'b0, trap};

endmodule

`default_nettype wire
