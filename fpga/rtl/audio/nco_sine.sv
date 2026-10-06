// NCO: phase accumulator, quarter-wave sine ROM and saw from the phase.
// Sample n is computed from phase (n + 1) * phase_inc; outputs are valid 3 clk after en
// and held until the next en. Bit-exact model: fpga/model/synthmodel/nco.py.
`default_nettype none

module nco_sine #(
    parameter int PHASE_W = 32,
    parameter int DATA_W  = 18,
    parameter int LUT_AW  = 10
) (
    input  wire                      clk,
    input  wire                      rst,
    input  wire                      en,
    input  wire        [PHASE_W-1:0] phase_inc,
    output logic signed [DATA_W-1:0] sine,
    output logic signed [DATA_W-1:0] saw
);

    logic [PHASE_W-1:0] phase;
    logic [1:0]         v;  // pipeline valid: v[0] phase updated, v[1] ROM data ready
    logic [1:0]         quad;
    logic               neg_q;  // quadrants 2, 3
    logic [LUT_AW-1:0]  idx, addr;
    logic [DATA_W-2:0]  rom_q;
    logic [DATA_W-1:0]  saw_d, saw_q;

    assign quad  = phase[PHASE_W-1 -: 2];
    assign idx   = phase[PHASE_W-3 -: LUT_AW];
    assign addr  = quad[0] ? ~idx : idx;               // mirror in quadrants 1 and 3
    assign saw_d = {~phase[PHASE_W-1], phase[PHASE_W-2 -: DATA_W-1]};

    sine_quarter_rom #(
        .AW(LUT_AW),
        .DW(DATA_W - 1)
    ) u_rom (
        .clk (clk),
        .addr(addr),
        .data(rom_q)
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            phase  <= '0;
            v      <= '0;
            neg_q  <= 1'b0;
            saw_q  <= '0;
            sine   <= '0;
            saw    <= '0;
        end else begin
            v <= {v[0], en};
            if (en)
                phase <= phase + phase_inc;
            if (v[0]) begin
                neg_q  <= quad[1];
                saw_q  <= saw_d;
            end
            if (v[1]) begin
                sine <= neg_q ? -$signed({1'b0, rom_q}) : $signed({1'b0, rom_q});
                saw  <= $signed(saw_q);
            end
        end
    end

endmodule

`default_nettype wire
