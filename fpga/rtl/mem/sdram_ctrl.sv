// SDR SDRAM controller for the external memory port (Tang Nano 20K: the GW2AR-18 embedded
// 64 Mbit SDRAM, 2M x 32, 4 banks x 2048 rows x 256 columns). One word per access:
// ACTIVE -> READ/WRITE with auto precharge; refresh has priority; CAS latency CL, burst 1.
// Word address = {bank, row, column}. Read data are sampled CL + RD_EXTRA clocks after the
// clock that samples READ (RD_EXTRA: input registers / clock phase on the board).
// DQ is split (dq_o, dq_oe, dq_i); the tristate buffer and the SDRAM clock are in the board top.
// Protocol of the request port: see mem_arb.sv. Verified by fpga/sim/unit/test_sdram.py
// against a model that checks command timing.
`default_nettype none

module sdram_ctrl #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int AW         = 24,
    parameter int COL_W      = 8,
    parameter int ROW_W      = 11,
    parameter int BANK_W     = 2,
    parameter int CL         = 2,
    parameter int RD_EXTRA   = 0,
    parameter int T_RP_NS    = 20,
    parameter int T_RCD_NS   = 20,
    parameter int T_RC_NS    = 70,     // also tRFC
    parameter int T_WR_CLK   = 2,
    parameter int T_REF_NS   = 7800,   // refresh interval (4096 rows / 64 ms = 15.6 us, halved)
    parameter int T_INIT_US  = 200
) (
    input  wire                     clk,
    input  wire                     rst,
    input  wire                     req,
    input  wire                     we,
    input  wire  [AW-1:0]           addr,
    input  wire  [31:0]             wdata,
    input  wire  [3:0]              be,
    output logic                    ack,
    output logic [31:0]             rdata,
    output logic                    ready,   // init done
    output logic                    sd_cke,
    output logic                    sd_cs_n,
    output logic                    sd_ras_n,
    output logic                    sd_cas_n,
    output logic                    sd_we_n,
    output logic [BANK_W-1:0]       sd_ba,
    output logic [ROW_W-1:0]        sd_addr,
    output logic [3:0]              sd_dqm,
    output logic [31:0]             sd_dq_o,
    output logic                    sd_dq_oe,
    input  wire  [31:0]             sd_dq_i
);

    function automatic int clk_of(input int ns);
        return int'((longint'(ns) * SYS_CLK_HZ + 999_999_999) / 1_000_000_000);
    endfunction

    localparam int TRP   = clk_of(T_RP_NS) < 1 ? 1 : clk_of(T_RP_NS);
    localparam int TRCD  = clk_of(T_RCD_NS) < 1 ? 1 : clk_of(T_RCD_NS);
    localparam int TRC   = clk_of(T_RC_NS);
    localparam int TREF  = clk_of(T_REF_NS);
    localparam int TINIT = clk_of(T_INIT_US * 1000);
    localparam int TMRD  = 2;
    // after READ with auto precharge: data at CL (+ RD_EXTRA), bank idle after 1 + tRP;
    // after WRITE with auto precharge: tWR + tRP. Both also keep tRC from ACTIVE.
    localparam int RD_WAIT = CL + RD_EXTRA;
    localparam int WR_WAIT = T_WR_CLK + TRP;
    localparam int CW      = $clog2(TINIT + 1) + 1;

    // commands {cs_n, ras_n, cas_n, we_n}
    localparam logic [3:0] C_NOP = 4'b0111, C_ACT = 4'b0011, C_RD = 4'b0101, C_WR = 4'b0100,
                           C_PRE = 4'b0010, C_REF = 4'b0001, C_MRS = 4'b0000;

    typedef enum logic [2:0] {S_INIT, S_PREALL, S_REF1, S_REF2, S_MRS, S_IDLE, S_RW, S_WAIT} state_t;
    state_t state;

    logic [CW-1:0]  cnt;       // wait counter for the current state
    logic [CW-1:0]  rc_cnt;    // clocks since ACTIVE (tRC)
    logic [$clog2(TREF + 1):0] ref_cnt;
    logic           ref_due, op_we;

    wire [COL_W-1:0]  col  = addr[COL_W-1:0];
    wire [ROW_W-1:0]  row  = addr[COL_W +: ROW_W];
    wire [BANK_W-1:0] bank = addr[COL_W + ROW_W +: BANK_W];

    task automatic cmd(input logic [3:0] c);
        {sd_cs_n, sd_ras_n, sd_cas_n, sd_we_n} <= c;
    endtask

    always_ff @(posedge clk) begin
        cmd(C_NOP);
        sd_dq_oe <= 1'b0;
        ack      <= 1'b0;
        if (cnt != '0) cnt <= cnt - 1'b1;
        if (rc_cnt != '0) rc_cnt <= rc_cnt - 1'b1;
        if (ref_cnt != '0) ref_cnt <= ref_cnt - 1'b1;
        else if (ready) ref_due <= 1'b1;

        if (rst) begin
            state    <= S_INIT;
            cnt      <= CW'(TINIT);
            rc_cnt   <= '0;
            ref_cnt  <= '0;
            ref_due  <= 1'b0;
            ready    <= 1'b0;
            sd_cke   <= 1'b1;
            sd_dqm   <= 4'hF;
            sd_ba    <= '0;
            sd_addr  <= '0;
        end else begin
            case (state)
                S_INIT: if (cnt == '0) begin
                    cmd(C_PRE);
                    sd_addr[10] <= 1'b1;  // all banks
                    cnt   <= CW'(TRP - 1);
                    state <= S_PREALL;
                end
                S_PREALL: if (cnt == '0) begin
                    cmd(C_REF);
                    cnt   <= CW'(TRC - 1);
                    state <= S_REF1;
                end
                S_REF1: if (cnt == '0) begin
                    cmd(C_REF);
                    cnt   <= CW'(TRC - 1);
                    state <= S_REF2;
                end
                S_REF2: if (cnt == '0) begin
                    cmd(C_MRS);
                    sd_ba   <= '0;
                    // burst 1, sequential, CAS latency, burst write = programmed length
                    sd_addr <= ROW_W'({4'b0000, 3'(CL), 1'b0, 3'b000});
                    cnt     <= CW'(TMRD - 1);
                    state   <= S_MRS;
                end
                S_MRS: if (cnt == '0) begin
                    ready   <= 1'b1;
                    ref_cnt <= '0;
                    state   <= S_IDLE;
                end
                S_IDLE: if (rc_cnt == '0 && cnt == '0) begin
                    if (ref_due) begin
                        cmd(C_REF);
                        ref_due <= 1'b0;
                        ref_cnt <= ($bits(ref_cnt))'(TREF - 1);
                        cnt     <= CW'(TRC - 1);
                    end else if (req && !ack) begin
                        cmd(C_ACT);
                        sd_ba   <= bank;
                        sd_addr <= row;
                        op_we   <= we;
                        rc_cnt  <= CW'(TRC - 1);
                        cnt     <= CW'(TRCD - 1);
                        state   <= S_RW;
                    end
                end
                S_RW: if (cnt == '0) begin
                    sd_addr <= ROW_W'({1'b1, 10'(col)});  // A10: auto precharge
                    if (op_we) begin
                        cmd(C_WR);
                        sd_dq_o  <= wdata;
                        sd_dq_oe <= 1'b1;
                        sd_dqm   <= ~be;
                        cnt      <= CW'(WR_WAIT);
                    end else begin
                        cmd(C_RD);
                        sd_dqm   <= 4'h0;
                        cnt      <= CW'(RD_WAIT);
                    end
                    state <= S_WAIT;
                end
                S_WAIT: begin
                    // READ: sampled at the clock after issue; data CL (+ extra) clocks later
                    if (!op_we && cnt == '0) rdata <= sd_dq_i;
                    if (cnt == '0) begin
                        sd_dqm <= 4'hF;
                        ack    <= 1'b1;
                        cnt    <= op_we ? '0 : CW'(TRP);
                        state  <= S_IDLE;
                    end
                end
                default: state <= S_IDLE;
            endcase
        end
    end

    wire unused = &{1'b0, addr};

endmodule

`default_nettype wire
