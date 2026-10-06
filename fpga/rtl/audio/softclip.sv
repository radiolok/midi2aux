// Soft clipper: linear up to 1.0 МЕ, tanh knee to 1.25 МЕ (DAC full scale).
// Bit-exact model: fpga/model/synthmodel/softclip.py. Latency 3 clk, one sample per clk.
`default_nettype none

module softclip #(
    parameter int IN_W = 20  // Q(IN_W-16).16
) (
    input  wire                    clk,
    input  wire signed [IN_W-1:0]  x,
    output logic signed [17:0]     y
);

    localparam logic [IN_W-1:0] T = IN_W'(65536);

    // stage 1: |x| - T, knee position, ROM address
    logic [IN_W-1:0] a;
    logic [IN_W+1:0] u;
    logic            neg1, lin1, sat1;
    logic [8:0]      fr1;
    logic signed [17:0] x1;

    assign a = x[IN_W-1] ? -x : x;
    assign u = {a - T, 2'b00};

    logic [26:0] rom_q;
    tanh_rom u_rom (.clk(clk), .addr(u[17:9]), .data(rom_q));

    always_ff @(posedge clk) begin
        neg1 <= x[IN_W-1];
        lin1 <= a <= T;
        sat1 <= u >= (IN_W+2)'(4 << 16);
        fr1  <= u[8:0];
        x1   <= 18'(x);
    end

    // stage 2: interpolate
    localparam logic [16:0] T_LAST = 17'd65492;  // round(tanh(4) * 2^16) = TANH[512] (softclip._LAST)
    logic [18:0] prod;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [16:0] t2;  // only t2 >> 2 is used
    /* verilator lint_on UNUSEDSIGNAL */
    logic        neg2, lin2;
    logic signed [17:0] x2;

    assign prod = rom_q[26:17] * fr1;

    always_ff @(posedge clk) begin
        t2   <= sat1 ? T_LAST : rom_q[16:0] + 17'(prod >> 9);
        neg2 <= neg1;
        lin2 <= lin1;
        x2   <= x1;
    end

    // stage 3: output
    logic [17:0] mag;
    assign mag = 18'(65536) + {3'b0, t2[16:2]};

    always_ff @(posedge clk) begin
        if (lin2)      y <= x2;
        else if (neg2) y <= -$signed(mag);
        else           y <= $signed(mag);
    end

endmodule

`default_nettype wire
