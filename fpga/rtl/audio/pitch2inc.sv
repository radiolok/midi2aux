// Log-domain pitch -> NCO phase increment, 3 clk latency, one conversion per clk.
// pitch = log2(inc) * 2^16 (oct = [20:16], frac = [15:0]); 2^frac from exp2_rom with
// linear interpolation (6 bits). Bit-exact model: fpga/model/synthmodel/pitch.py.
`default_nettype none

module pitch2inc (
    input  wire         clk,
    input  wire         rst,
    input  wire  [20:0] pitch,
    input  wire         in_valid,
    output logic [31:0] inc,
    output logic        out_valid
);

    logic [25:0] rom_q;
    logic [4:0]  oct_q, oct_qq;
    logic [5:0]  f_q;
    logic [17:0] mant;
    logic [1:0]  v;

    exp2_rom u_rom (
        .clk (clk),
        .addr(pitch[15:6]),
        .data(rom_q)
    );

    // (T + (D * f) >> 6) << oct >> 17
    /* verilator lint_off UNUSEDSIGNAL */
    logic [13:0] prod;     // low 6 bits: fraction, dropped
    logic [48:0] shifted;  // low 17 bits: fraction, dropped
    /* verilator lint_on UNUSEDSIGNAL */

    assign prod    = rom_q[25:18] * f_q;
    assign shifted = {31'b0, mant} << oct_qq;

    always_ff @(posedge clk) begin
        if (rst) begin
            v         <= '0;
            out_valid <= 1'b0;
            oct_q     <= '0;
            oct_qq    <= '0;
            f_q       <= '0;
            mant      <= '0;
            inc       <= '0;
        end else begin
            v         <= {v[0], in_valid};
            out_valid <= v[1];
            oct_q     <= pitch[20:16];
            f_q       <= pitch[5:0];
            oct_qq    <= oct_q;
            mant      <= rom_q[17:0] + {10'b0, prod[13:6]};
            inc       <= shifted[48:17];
        end
    end

endmodule

`default_nettype wire
