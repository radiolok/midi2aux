// Synchronous FIFO, first-word-fall-through: rd_data is valid while !empty.
// Push when full is dropped and sets the sticky overflow flag.
`default_nettype none

module sync_fifo #(
    parameter int WIDTH = 24,
    parameter int DEPTH = 32  // power of two
) (
    input  wire                     clk,
    input  wire                     rst,
    input  wire                     wr_en,
    input  wire [WIDTH-1:0]         wr_data,
    input  wire                     rd_en,
    output logic [WIDTH-1:0]        rd_data,
    output logic                    empty,
    output logic                    full,
    output logic [$clog2(DEPTH):0]  count,
    output logic                    overflow,
    input  wire                     clr_overflow
);

    localparam int AW = $clog2(DEPTH);

    generate
        if ((1 << AW) != DEPTH) begin : g_bad_params
            sync_fifo_depth_must_be_power_of_two u_bad ();
        end
    endgenerate

    logic [WIDTH-1:0] mem [DEPTH];
    logic [AW:0]      wp, rp;
    logic             do_wr, do_rd;

    assign empty   = (wp == rp);
    assign full    = (wp[AW-1:0] == rp[AW-1:0]) && (wp[AW] != rp[AW]);
    assign count   = wp - rp;
    assign rd_data = mem[rp[AW-1:0]];
    assign do_wr   = wr_en && !full;
    assign do_rd   = rd_en && !empty;

    always_ff @(posedge clk) begin
        if (do_wr) mem[wp[AW-1:0]] <= wr_data;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            wp       <= '0;
            rp       <= '0;
            overflow <= 1'b0;
        end else begin
            if (do_wr) wp <= wp + 1'b1;
            if (do_rd) rp <= rp + 1'b1;
            if (wr_en && full) overflow <= 1'b1;
            else if (clr_overflow) overflow <= 1'b0;
        end
    end

endmodule

`default_nettype wire
