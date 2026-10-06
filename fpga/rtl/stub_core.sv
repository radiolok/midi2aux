// Stage 0 stub core (portable, no vendor primitives):
//   left  = sine TONE_HZ, right = saw of the same NCO, I2S out;
//   MIDI UART bytes exported for the testbench, LED toggles per byte;
//   LED blink at BLINK_HZ.
`default_nettype none

module stub_core #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int FS_HZ      = 48_000,
    parameter int DATA_W     = 18,
    parameter int PHASE_W    = 32,
    parameter int LUT_AW     = 10,
    parameter int TONE_HZ    = 440,
    parameter int BLINK_HZ   = 1,
    parameter int MIDI_BAUD  = 31_250
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        midi_rx,
    output logic       i2s_bck,
    output logic       i2s_lrck,
    output logic       i2s_din,
    output logic       dac_xsmt,   // PCM5102A soft mute, 1 = play
    output logic       led_blink,
    output logic       led_midi,
    output logic [7:0] midi_data,
    output logic       midi_valid
);

    localparam int BCK_HALF = (SYS_CLK_HZ + 64 * FS_HZ) / (128 * FS_HZ);
    // increment for TONE_HZ at the actual fs = SYS_CLK_HZ / (128 * BCK_HALF)
    localparam logic [63:0] PHASE_INC64 =
        ((64'd1 << PHASE_W) * 64'(TONE_HZ) * 64'd128 * 64'(BCK_HALF) + 64'(SYS_CLK_HZ) / 64'd2)
        / 64'(SYS_CLK_HZ);
    localparam logic [PHASE_W-1:0] PHASE_INC = PHASE_INC64[PHASE_W-1:0];

    // ---------------------------------------------------------------- audio
    logic                     bck_fall_stb, audio_tick;
    logic [5:0]               slot_next;
    logic signed [DATA_W-1:0] sine, saw;

    audio_clkgen #(
        .SYS_CLK_HZ(SYS_CLK_HZ),
        .FS_HZ     (FS_HZ),
        .BCK_HALF  (BCK_HALF)
    ) u_clkgen (
        .clk         (clk),
        .rst         (rst),
        .bck         (i2s_bck),
        .bck_fall_stb(bck_fall_stb),
        .slot_next   (slot_next),
        .audio_tick  (audio_tick)
    );

    nco_sine #(
        .PHASE_W(PHASE_W),
        .DATA_W (DATA_W),
        .LUT_AW (LUT_AW)
    ) u_nco (
        .clk      (clk),
        .rst      (rst),
        .en       (audio_tick),
        .phase_inc(PHASE_INC),
        .sine     (sine),
        .saw      (saw)
    );

    i2s_tx #(
        .DATA_W(DATA_W)
    ) u_i2s (
        .clk         (clk),
        .rst         (rst),
        .bck_fall_stb(bck_fall_stb),
        .slot_next   (slot_next),
        .left        (sine),
        .right       (saw),
        .lrck        (i2s_lrck),
        .din         (i2s_din)
    );

    always_ff @(posedge clk) begin
        if (rst) dac_xsmt <= 1'b0;
        else     dac_xsmt <= 1'b1;
    end

    // ----------------------------------------------------------------- MIDI
    uart_rx #(
        .SYS_CLK_HZ(SYS_CLK_HZ),
        .BAUD      (MIDI_BAUD)
    ) u_midi_rx (
        .clk  (clk),
        .rst  (rst),
        .rx   (midi_rx),
        .data (midi_data),
        .valid(midi_valid)
    );

    always_ff @(posedge clk) begin
        if (rst)             led_midi <= 1'b0;
        else if (midi_valid) led_midi <= ~led_midi;
    end

    // ---------------------------------------------------------------- blink
    localparam int BLINK_DIV = SYS_CLK_HZ / (2 * BLINK_HZ);
    localparam int BW        = $clog2(BLINK_DIV);

    logic [BW-1:0] blink_cnt;

    always_ff @(posedge clk) begin
        if (rst) begin
            blink_cnt <= '0;
            led_blink <= 1'b0;
        end else if (blink_cnt == BW'(BLINK_DIV - 1)) begin
            blink_cnt <= '0;
            led_blink <= ~led_blink;
        end else begin
            blink_cnt <= blink_cnt + BW'(1);
        end
    end

endmodule

`default_nettype wire
