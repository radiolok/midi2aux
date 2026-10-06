// Q2.16 sample (1.0 = machine unit, +-10 V) -> DAC code: x * 1.6, saturated,
// so 1.0 is 0.8 of the DAC full scale (+-12.5 V). Model: synthmodel.fixed.to_dac.
// 1 clk latency.
`default_nettype none

module dac_scale #(
    parameter int DATA_W = 18
) (
    input  wire                      clk,
    input  wire signed [DATA_W-1:0]  x,
    output logic signed [DATA_W-1:0] y
);

    localparam logic signed [18:0] GAIN = 19'sd104858;  // round(1.6 * 2^16)
    localparam logic signed [DATA_W+2:0] MAXV = (DATA_W+3)'((1 << (DATA_W - 1)) - 1);
    localparam logic signed [DATA_W+2:0] MINV = -(DATA_W+3)'(1 << (DATA_W - 1));

    logic signed [DATA_W+18:0] p;
    logic signed [DATA_W+2:0]  s;

    assign p = x * GAIN;
    assign s = (DATA_W+3)'(p >>> 16);

    always_ff @(posedge clk) begin
        if (s > MAXV)      y <= MAXV[DATA_W-1:0];
        else if (s < MINV) y <= MINV[DATA_W-1:0];
        else               y <= s[DATA_W-1:0];
    end

endmodule

`default_nettype wire
