// I2S transmitter (Philips): 32-bit slots, DATA_W-bit samples MSB first, low bits zero.
// LRCK = 0 left, 1 right; LRCK and DIN change on the BCK falling edge, MSB one BCK
// after the LRCK edge. Samples are latched at the frame start (audio_tick).
`default_nettype none

module i2s_tx #(
    parameter int DATA_W = 18
) (
    input  wire                     clk,
    input  wire                     rst,
    input  wire                     bck_fall_stb,
    input  wire [5:0]               slot_next,
    input  wire signed [DATA_W-1:0] left,
    input  wire signed [DATA_W-1:0] right,
    output logic                    lrck,
    output logic                    din
);

    localparam int PAD = 32 - DATA_W;

    generate
        if (DATA_W > 32 || DATA_W < 1) begin : g_bad_params
            i2s_tx_data_w_must_be_1_to_32 u_bad ();
        end
    endgenerate

    logic [63:0] sr;

    always_ff @(posedge clk) begin
        if (rst) begin
            sr   <= '0;
            lrck <= 1'b0;
            din  <= 1'b0;
        end else if (bck_fall_stb) begin
            lrck <= slot_next[5];
            din  <= sr[63];  // at slot 0 this is the LSB of the previous right word
            if (slot_next == 6'd0)
                sr <= {left, {PAD{1'b0}}, right, {PAD{1'b0}}};
            else
                sr <= {sr[62:0], 1'b0};
        end
    end

endmodule

`default_nettype wire
