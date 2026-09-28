// Stage 1 core: one voice like MIDI2AUX, no CPU.
//   MIDI UART -> parser -> event FIFO -> last-note logic (omni);
//   pitch bend +-2 semitones; All Notes Off (CC123), All Sound Off (CC120), Stop (FC);
//   left  = square +-0.5 МЕ with a 2.6 ms declick ramp;
//   right = gate CV (+1.0 МЕ = +10 V while a note sounds).
`default_nettype none

module mono_core #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int FS_HZ      = 48_000,
    parameter int DATA_W     = 18,
    parameter int BLINK_HZ   = 1,
    parameter int MIDI_BAUD  = 31_250,
    parameter int FIFO_DEPTH = 16
) (
    input  wire  clk,
    input  wire  rst,
    input  wire  midi_rx,
    output logic i2s_bck,
    output logic i2s_lrck,
    output logic i2s_din,
    output logic dac_xsmt,
    output logic led_blink,
    output logic led_midi,
    output logic led_gate
);

    // log2(x) * 2^16, floor; integer-only (model: synthmodel.pitch.log2_q16)
    function automatic logic [31:0] log2_q16(input logic [63:0] x);
        logic [63:0] y;
        logic [31:0] r;
        int          msb;
        msb = 0;
        for (int i = 0; i < 64; i++)
            if (x[i]) msb = i;
        y = (x << 30) >> msb;
        r = 32'(msb);
        for (int i = 0; i < 16; i++) begin
            y = (y * y) >> 30;
            r = r << 1;
            if (y >= (64'd2 << 30)) begin
                y = y >> 1;
                r = r | 32'd1;
            end
        end
        return r;
    endfunction

    localparam int BCK_HALF = (SYS_CLK_HZ + 64 * FS_HZ) / (128 * FS_HZ);
    localparam logic [63:0] INC_A4 =
        ((64'd440 << 32) * 64'd128 * 64'(BCK_HALF) + 64'(SYS_CLK_HZ) / 64'd2) / 64'(SYS_CLK_HZ);
    localparam logic [31:0] P_A4_32 = log2_q16(INC_A4);
    localparam logic signed [22:0] P_A4 = 23'(P_A4_32);

    localparam logic signed [DATA_W-1:0] AMP_MAX = DATA_W'(32768);  // 0.5 МЕ
    localparam logic signed [DATA_W-1:0] AMP_STEP = DATA_W'(256);
    localparam logic signed [DATA_W-1:0] GATE_CV = DATA_W'(65536);  // 1.0 МЕ

    // ---------------------------------------------------------------- MIDI
    logic [7:0]  rx_data;
    logic        rx_valid;
    logic [7:0]  ev_status, ev_d1, ev_d2;
    logic        ev_valid;
    logic [23:0] ev;
    logic        ev_empty;

    uart_rx #(.SYS_CLK_HZ(SYS_CLK_HZ), .BAUD(MIDI_BAUD)) u_uart (
        .clk(clk), .rst(rst), .rx(midi_rx), .data(rx_data), .valid(rx_valid)
    );

    midi_parser u_parser (
        .clk(clk), .rst(rst), .in_data(rx_data), .in_valid(rx_valid),
        .ev_status(ev_status), .ev_d1(ev_d1), .ev_d2(ev_d2), .ev_valid(ev_valid)
    );

    /* verilator lint_off PINCONNECTEMPTY */
    sync_fifo #(.WIDTH(24), .DEPTH(FIFO_DEPTH)) u_fifo (
        .clk(clk), .rst(rst),
        .wr_en(ev_valid), .wr_data({ev_status, ev_d1, ev_d2}),
        .rd_en(!ev_empty), .rd_data(ev), .empty(ev_empty),
        .full(), .count(), .overflow(), .clr_overflow(1'b0)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    logic [6:0]         note;
    logic               gate;
    logic signed [14:0] bend;  // -8192..8191

    always_ff @(posedge clk) begin
        if (rst) begin
            note     <= 7'd69;
            gate     <= 1'b0;
            bend     <= '0;
            led_midi <= 1'b0;
        end else if (!ev_empty) begin
            led_midi <= ~led_midi;
            case (ev[23:20])
                4'h9: begin
                    note <= ev[14:8];
                    gate <= 1'b1;
                end
                4'h8: if (ev[14:8] == note) gate <= 1'b0;
                4'hB: if (ev[15:8] == 8'd123 || ev[15:8] == 8'd120) gate <= 1'b0;
                4'hE: bend <= $signed({1'b0, ev[6:0], ev[14:8]}) - 15'sd8192;
                4'hF: if (ev[23:16] == 8'hFC) gate <= 1'b0;
                default: ;
            endcase
        end
    end

    assign led_gate = gate;

    wire unused_ev = ev[7];  // data bytes are 7-bit

    // --------------------------------------------------------------- pitch
    // semitone = 2^16 / 12 = 349525 >> 6; bend +-8192 -> +-2 semitones: * 2 * 349525 >> 19
    logic signed [22:0] p_note, p_bend, p_sum;
    logic [20:0]        pitch;
    logic signed [35:0] note_mul, bend_mul;

    assign note_mul = $signed({1'b0, 28'(note)} - 29'sd69) * 36'sd349525;
    assign bend_mul = 36'(bend) * 36'sd699050;
    assign p_note   = 23'(note_mul >>> 6);
    assign p_bend   = 23'(bend_mul >>> 19);
    assign p_sum    = P_A4 + p_note + p_bend;
    assign pitch    = p_sum < 0 ? '0 : p_sum > 23'sd2097151 ? '1 : p_sum[20:0];

    // ---------------------------------------------------------------- audio
    logic        bck_fall_stb, audio_tick;
    logic [5:0]  slot_next;
    logic [31:0] inc, phase;
    logic        inc_valid;

    audio_clkgen #(.SYS_CLK_HZ(SYS_CLK_HZ), .FS_HZ(FS_HZ), .BCK_HALF(BCK_HALF)) u_clkgen (
        .clk(clk), .rst(rst), .bck(i2s_bck), .bck_fall_stb(bck_fall_stb),
        .slot_next(slot_next), .audio_tick(audio_tick)
    );

    pitch2inc u_p2i (
        .clk(clk), .rst(rst), .pitch(pitch), .in_valid(audio_tick),
        .inc(inc), .out_valid(inc_valid)
    );

    logic signed [DATA_W-1:0] amp, sq, left_q, right_q, left, right;

    always_ff @(posedge clk) begin
        if (rst) begin
            phase <= '0;
            amp   <= '0;
        end else if (inc_valid) begin
            phase <= phase + inc;
            if (gate && amp < AMP_MAX)       amp <= amp + AMP_STEP;
            else if (!gate && amp > 0)       amp <= amp - AMP_STEP;
        end
    end

    assign sq      = phase[31] ? -amp : amp;
    assign right_q = gate ? GATE_CV : '0;

    dac_scale #(.DATA_W(DATA_W)) u_dac_l (.clk(clk), .x(sq), .y(left_q));
    dac_scale #(.DATA_W(DATA_W)) u_dac_r (.clk(clk), .x(right_q), .y(right));
    assign left = left_q;

    i2s_tx #(.DATA_W(DATA_W)) u_i2s (
        .clk(clk), .rst(rst), .bck_fall_stb(bck_fall_stb), .slot_next(slot_next),
        .left(left), .right(right), .lrck(i2s_lrck), .din(i2s_din)
    );

    always_ff @(posedge clk) begin
        if (rst) dac_xsmt <= 1'b0;
        else     dac_xsmt <= 1'b1;
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
