// Tang Nano 20K top: synth_core (PicoRV32 SoC + audio). Select with CORE=synth (default).
// LEDs (active low): 0..3 firmware GPIO, 4 MIDI activity, 5 CPU trap.
`default_nettype none

module top (
    input  wire       clk_27m,
    input  wire       btn_rst,    // S1, active high
    input  wire       btn_user,   // S2, active high
    input  wire       midi_rx,    // after the optocoupler, idle high
    input  wire       uart_rx,    // BL702 USB-UART
    output wire       uart_tx,
    output wire       flash_sck,
    output wire       flash_mosi,
    input  wire       flash_miso,
    output wire       flash_cs_n,
    output wire       sd_sck,     // TF card slot, SPI mode
    output wire       sd_mosi,
    input  wire       sd_miso,
    output wire       sd_cs_n,
    output wire       pot_sck,
    output wire       pot_mosi,
    input  wire       pot_miso,
    output wire       pot_cs_n,
    input  wire [3:0] enc_a,
    input  wire [3:0] enc_b,
    input  wire [3:0] enc_sw,
    output wire       lcd_sck,
    output wire       lcd_mosi,
    output wire       lcd_cs_n,
    output wire       lcd_dc,
    output wire       lcd_rst_n,
    output wire       lcd_bl,
    output wire       adc_convst_n,
    output wire       adc_cs_n,
    output wire       adc_sclk,
    input  wire       adc_sdo1,
    input  wire       adc_sdo2,
    input  wire       sync_in,    // SYNC comparator output
    output wire       i2s_bck,
    output wire       i2s_lrck,
    output wire       i2s_din,
    output wire       dac_xsmt,
    output wire [5:0] led_n,
    // GW2AR-18 embedded SDRAM (64 Mbit, 2M x 32): fixed port names, no pin constraints
    output wire        O_sdram_clk,
    output wire        O_sdram_cke,
    output wire        O_sdram_cs_n,
    output wire        O_sdram_cas_n,
    output wire        O_sdram_ras_n,
    output wire        O_sdram_wen_n,
    output wire [3:0]  O_sdram_dqm,
    output wire [10:0] O_sdram_addr,
    output wire [1:0]  O_sdram_ba,
    inout  wire [31:0] IO_sdram_dq
);

    localparam int SYS_CLK_HZ = 99_000_000;  // see pll_sys.v
    localparam int MEM_WORDS  = 2 * 1024 * 1024;  // embedded SDRAM, 43 s of delay

    wire clk, pll_lock;

    pll_sys u_pll (
        .clkin (clk_27m),
        .clkout(clk),
        .lock  (pll_lock)
    );

    wire        arst = ~pll_lock | btn_rst;
    logic [3:0] rst_sr;
    wire        rst  = rst_sr[3];

    always_ff @(posedge clk or posedge arst) begin
        if (arst) rst_sr <= '1;
        else      rst_sr <= {rst_sr[2:0], 1'b0};
    end

    logic [5:0] led;
    logic       trap;

    logic        xm_req, xm_we, xm_ack;
    logic [23:0] xm_addr;
    logic [31:0] xm_wdata, xm_rdata;
    logic [3:0]  xm_be;

    synth_core #(
        .SYS_CLK_HZ     (SYS_CLK_HZ),
        .RAM_BYTES      (32768),
        .FW_FLASH_OFFSET(32'h0050_0000),
        .NUM_VOICES     (32),
        .NUM_SLOTS      (6),
        .SLOT_TYPES     (48'h04_03_02_02_01_01),  // MATH, MATH, DELAY, DELAY, CHORUS, REVERB
        .MEM_WORDS      (MEM_WORDS)
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
        .sd_sck    (sd_sck),
        .sd_mosi   (sd_mosi),
        .sd_miso   (sd_miso),
        .sd_cs_n   (sd_cs_n),
        .pot_sck   (pot_sck),
        .pot_mosi  (pot_mosi),
        .pot_miso  (pot_miso),
        .pot_cs_n  (pot_cs_n),
        .enc_a     (enc_a),
        .enc_b     (enc_b),
        .enc_sw    (enc_sw),
        .lcd_sck   (lcd_sck),
        .lcd_mosi  (lcd_mosi),
        .lcd_cs_n  (lcd_cs_n),
        .lcd_dc    (lcd_dc),
        .lcd_rst_n (lcd_rst_n),
        .lcd_bl    (lcd_bl),
        .adc_convst_n(adc_convst_n),
        .adc_cs_n  (adc_cs_n),
        .adc_sclk  (adc_sclk),
        .adc_sdo1  (adc_sdo1),
        .adc_sdo2  (adc_sdo2),
        .sync_in   (sync_in),
        .xm_req    (xm_req),
        .xm_we     (xm_we),
        .xm_addr   (xm_addr),
        .xm_wdata  (xm_wdata),
        .xm_be     (xm_be),
        .xm_ack    (xm_ack),
        .xm_rdata  (xm_rdata),
        .i2s_bck   (i2s_bck),
        .i2s_lrck  (i2s_lrck),
        .i2s_din   (i2s_din),
        .dac_xsmt  (dac_xsmt),
        .led       (led),
        .btn       ({1'b0, btn_user}),
        .trap      (trap)
    );

    logic [31:0] dq_o;
    logic        dq_oe;

    /* verilator lint_off PINCONNECTEMPTY */
    sdram_ctrl #(.SYS_CLK_HZ(SYS_CLK_HZ)) u_sdram (
        .clk(clk), .rst(rst), .req(xm_req), .we(xm_we), .addr(xm_addr), .wdata(xm_wdata), .be(xm_be),
        .ack(xm_ack), .rdata(xm_rdata), .ready(),
        .sd_cke(O_sdram_cke), .sd_cs_n(O_sdram_cs_n), .sd_ras_n(O_sdram_ras_n), .sd_cas_n(O_sdram_cas_n),
        .sd_we_n(O_sdram_wen_n), .sd_ba(O_sdram_ba), .sd_addr(O_sdram_addr), .sd_dqm(O_sdram_dqm),
        .sd_dq_o(dq_o), .sd_dq_oe(dq_oe), .sd_dq_i(IO_sdram_dq)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // SDRAM clock in phase with clk: read data are sampled CL + 1 clocks after READ
    // (sdram_ctrl RD_EXTRA = 0). Check the phase on the board (HO-07).
    assign O_sdram_clk = clk;
    assign IO_sdram_dq = dq_oe ? dq_o : 32'bz;

    assign led_n = ~led;

    wire unused = &{1'b0, trap};

endmodule

`default_nettype wire
