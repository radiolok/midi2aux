// External memory port on block RAM (Tang Nano 9K, simulation): WORDS words of DW bits,
// read data sign-extended from DW to 32 bits; byte enables are honoured only for DW = 32
// (DW < 32: any enable writes the word). Ack one cycle after req; addresses wrap.
`default_nettype none

module mem_bram #(
    parameter int AW    = 24,
    parameter int WORDS = 4096,
    parameter int DW    = 18
) (
    input  wire           clk,
    input  wire           rst,
    input  wire           req,
    input  wire           we,
    input  wire  [AW-1:0] addr,
    input  wire  [31:0]   wdata,
    input  wire  [3:0]    be,
    output logic          ack,
    output logic [31:0]   rdata
);

    localparam int IW = $clog2(WORDS);

    wire [IW-1:0] a = addr[IW-1:0];
    wire          go = req && !ack;
    logic [DW-1:0] q;

    always_ff @(posedge clk) ack <= go && !rst;

    if (DW == 32) begin : g_lanes  // byte lanes, like soc_ram
        for (genvar l = 0; l < 4; l++) begin : g_lane
            logic [7:0] mem [WORDS];
            always_ff @(posedge clk) begin
                if (go && we && be[l]) mem[a] <= wdata[8*l +: 8];
                if (go) q[8*l +: 8] <= mem[a];
            end
        end
    end else begin : g_word
        logic [DW-1:0] mem [WORDS];
        always_ff @(posedge clk) begin
            if (go && we && |be) mem[a] <= wdata[DW-1:0];
            if (go) q <= mem[a];
        end
    end

    assign rdata = 32'(signed'(q));

    wire unused = &{1'b0, addr, wdata};

endmodule

`default_nettype wire
