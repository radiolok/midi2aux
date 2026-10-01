// CPU RAM with byte enables: four 8-bit lanes (portable BSRAM inference),
// registered read. INIT (simulation only): $readmemh file of 32-bit words.
`default_nettype none

module soc_ram #(
    parameter int    BYTES = 32768,
    parameter string INIT  = ""
) (
    input  wire                           clk,
    input  wire                           en,
    input  wire  [3:0]                    we,
    input  wire  [$clog2(BYTES / 4)-1:0]  addr,
    input  wire  [31:0]                   wdata,
    output logic [31:0]                   rdata
);

    localparam int WORDS = BYTES / 4;

    logic [7:0] mem0 [WORDS];
    logic [7:0] mem1 [WORDS];
    logic [7:0] mem2 [WORDS];
    logic [7:0] mem3 [WORDS];

`ifdef VERILATOR
    logic [31:0] init_words [WORDS];
    initial begin
        if (INIT != "") begin
            for (int i = 0; i < WORDS; i++) init_words[i] = '0;
            $readmemh(INIT, init_words);
            for (int i = 0; i < WORDS; i++) begin
                mem0[i] = init_words[i][7:0];
                mem1[i] = init_words[i][15:8];
                mem2[i] = init_words[i][23:16];
                mem3[i] = init_words[i][31:24];
            end
        end
    end
`endif

    always_ff @(posedge clk) begin
        if (en) begin
            if (we[0]) mem0[addr] <= wdata[7:0];
            if (we[1]) mem1[addr] <= wdata[15:8];
            if (we[2]) mem2[addr] <= wdata[23:16];
            if (we[3]) mem3[addr] <= wdata[31:24];
            rdata <= {mem3[addr], mem2[addr], mem1[addr], mem0[addr]};
        end
    end

endmodule

`default_nettype wire
