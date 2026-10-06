// I2S bit clock and audio_tick from sys_clk by an integer divider.
// fs = SYS_CLK_HZ / (2 * BCK_HALF * 64), BCK = 64 * fs (two 32-bit slots).
// Model: fpga/model/synthmodel/clocks.py.
`default_nettype none

module audio_clkgen #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int FS_HZ      = 48_000,
    // sys_clk cycles per BCK half-period, default: nearest to FS_HZ
    parameter int BCK_HALF   = (SYS_CLK_HZ + 64 * FS_HZ) / (128 * FS_HZ)
) (
    input  wire        clk,
    input  wire        rst,
    output logic       bck,
    output logic       bck_fall_stb, // bck goes 1->0 on the next clk edge
    output logic [5:0] slot_next,    // bit slot (0..63) that starts at that edge
    output logic       audio_tick    // 1 clk at the frame start (slot 0)
);

    localparam int CW = (BCK_HALF > 1) ? $clog2(BCK_HALF) : 1;

    generate
        if (BCK_HALF < 2) begin : g_bad_params
            audio_clkgen_needs_sys_clk_ge_256_fs u_bad ();
        end
    endgenerate

    logic [CW-1:0] cnt;
    logic [5:0]    slot;
    logic          half_end;

    assign half_end     = (cnt == CW'(BCK_HALF - 1));
    assign bck_fall_stb = half_end & bck;
    assign slot_next    = slot + 6'd1;

    always_ff @(posedge clk) begin
        audio_tick <= 1'b0;
        if (rst) begin
            cnt  <= '0;
            bck  <= 1'b0;
            slot <= 6'd63;
        end else if (half_end) begin
            cnt <= '0;
            bck <= ~bck;
            if (bck) begin
                slot       <= slot_next;
                audio_tick <= (slot_next == 6'd0);
            end
        end else begin
            cnt <= cnt + CW'(1);
        end
    end

endmodule

`default_nettype wire
