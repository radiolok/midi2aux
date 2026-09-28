// External memory arbiter: two masters (A: audio slots, priority; B: CPU window), one slave.
// Protocol on every port: req is held (with we/addr/wdata/be) until ack (one cycle, rdata valid
// with it); the master drops req in the cycle after ack. A slave ignores req while ack is high.
`default_nettype none

module mem_arb #(
    parameter int AW = 24
) (
    input  wire           clk,
    input  wire           rst,
    input  wire           a_req,
    input  wire           a_we,
    input  wire  [AW-1:0] a_addr,
    input  wire  [31:0]   a_wdata,
    input  wire  [3:0]    a_be,
    output logic          a_ack,
    input  wire           b_req,
    input  wire           b_we,
    input  wire  [AW-1:0] b_addr,
    input  wire  [31:0]   b_wdata,
    input  wire  [3:0]    b_be,
    output logic          b_ack,
    output logic [31:0]   rdata,     // for both masters
    output logic          m_req,
    output logic          m_we,
    output logic [AW-1:0] m_addr,
    output logic [31:0]   m_wdata,
    output logic [3:0]    m_be,
    input  wire           m_ack,
    input  wire  [31:0]   m_rdata
);

    logic busy, gnt_b;

    always_ff @(posedge clk) begin
        if (rst) begin
            busy  <= 1'b0;
            gnt_b <= 1'b0;
        end else if (!busy) begin
            if (a_req) begin
                busy  <= 1'b1;
                gnt_b <= 1'b0;
            end else if (b_req) begin
                busy  <= 1'b1;
                gnt_b <= 1'b1;
            end
        end else if (m_ack) begin
            busy <= 1'b0;
        end
    end

    assign m_req   = busy && (gnt_b ? b_req : a_req);
    assign m_we    = gnt_b ? b_we : a_we;
    assign m_addr  = gnt_b ? b_addr : a_addr;
    assign m_wdata = gnt_b ? b_wdata : a_wdata;
    assign m_be    = gnt_b ? b_be : a_be;
    assign a_ack   = busy && !gnt_b && m_ack;
    assign b_ack   = busy && gnt_b && m_ack;
    assign rdata   = m_rdata;

endmodule

`default_nettype wire
