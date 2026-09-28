// Test top: mem_arb + mem_bram (32-bit words, byte enables), see test_mem.py.
`default_nettype none

module mem_arb_bram_tb (
    input  wire         clk,
    input  wire         rst,
    input  wire         a_req,
    input  wire         a_we,
    input  wire  [23:0] a_addr,
    input  wire  [31:0] a_wdata,
    input  wire  [3:0]  a_be,
    output logic        a_ack,
    input  wire         b_req,
    input  wire         b_we,
    input  wire  [23:0] b_addr,
    input  wire  [31:0] b_wdata,
    input  wire  [3:0]  b_be,
    output logic        b_ack,
    output logic [31:0] rdata
);

    logic        m_req, m_we, m_ack;
    logic [23:0] m_addr;
    logic [31:0] m_wdata, m_rdata;
    logic [3:0]  m_be;

    mem_arb u_arb (
        .clk(clk), .rst(rst),
        .a_req(a_req), .a_we(a_we), .a_addr(a_addr), .a_wdata(a_wdata), .a_be(a_be), .a_ack(a_ack),
        .b_req(b_req), .b_we(b_we), .b_addr(b_addr), .b_wdata(b_wdata), .b_be(b_be), .b_ack(b_ack),
        .rdata(rdata), .m_req(m_req), .m_we(m_we), .m_addr(m_addr), .m_wdata(m_wdata), .m_be(m_be),
        .m_ack(m_ack), .m_rdata(m_rdata)
    );

    mem_bram #(.WORDS(64), .DW(32)) u_ram (
        .clk(clk), .rst(rst), .req(m_req), .we(m_we), .addr(m_addr), .wdata(m_wdata), .be(m_be),
        .ack(m_ack), .rdata(m_rdata)
    );

endmodule

`default_nettype wire
