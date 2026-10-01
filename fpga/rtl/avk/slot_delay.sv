// Slot DELAY (TYPE_ID 2): delay line in external memory (MEM_BASE, MEM_SIZE words, one
// sample per 32-bit word), per sample: d = mem[wp - TIME]; mem[wp] = sat18(A + FB * d);
// y = sat18(DRY * A + WET * d). B is not used. MEM_SIZE = 0: y = A.
// PARAM0 TIME (samples, clamped to MEM_SIZE - 1)  PARAM1 FB  PARAM2 WET  PARAM3 DRY (Q2.16).
// Reset: TIME 0, FB 0, WET 0, DRY 1.0 (passes A). Model: fpga/model/synthmodel/avk.py (Slot).
//
// Standard slot interface + memory port (mem/mem_arb.sv): m_req is held until m_ack.
`default_nettype none

module slot_delay #(
    parameter int AW = 24  // word address width
) (
    input  wire                clk,
    input  wire                rst,
    input  wire                start,
    input  wire signed [17:0]  a,
    input  wire signed [17:0]  b,
    input  wire                p_we,
    input  wire  [3:0]         p_addr,
    input  wire  [31:0]        p_wdata,
    input  wire  [AW-1:0]      mem_base,
    input  wire  [AW-1:0]      mem_size,
    output logic               m_req,
    output logic               m_we,
    output logic [AW-1:0]      m_addr,
    output logic [31:0]        m_wdata,
    input  wire                m_ack,
    input  wire  [31:0]        m_rdata,
    output logic signed [17:0] y,
    output logic               done
);

    localparam logic signed [17:0] MAXV = 18'sd131071, MINV = -18'sd131072;

    logic [AW-1:0]      dtime, wp;
    logic signed [17:0] fb, wet, dry, d, xa;

    always_ff @(posedge clk) begin
        if (rst) begin
            dtime <= '0;
            fb    <= '0;
            wet   <= '0;
            dry   <= 18'sd65536;
        end else if (p_we) begin
            case (p_addr)
                4'd0: dtime <= p_wdata[AW-1:0];
                4'd1: fb    <= p_wdata[17:0];
                4'd2: wet   <= p_wdata[17:0];
                4'd3: dry   <= p_wdata[17:0];
                default: ;
            endcase
        end
    end

    function automatic logic signed [17:0] sat18(input logic signed [37:0] x);
        if (x > 38'(MAXV)) return MAXV;
        if (x < 38'(MINV)) return MINV;
        return x[17:0];
    endfunction

    wire [AW-1:0] wpe    = wp >= mem_size ? '0 : wp;  // MEM_SIZE may have been made smaller
    wire [AW-1:0] t      = dtime >= mem_size ? mem_size - 1'b1 : dtime;
    wire [AW-1:0] rd_off = wpe >= t ? wpe - t : wpe + mem_size - t;

    wire signed [35:0] fb_d  = fb * d;
    wire signed [35:0] dry_a = dry * xa;
    wire signed [35:0] wet_d = wet * d;
    wire signed [17:0] w     = sat18(38'(xa) + (38'(fb_d) >>> 16));

    typedef enum logic [1:0] {IDLE, RD, WR} state_t;
    state_t state;

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            state <= IDLE;
            m_req <= 1'b0;
            m_we  <= 1'b0;
            wp    <= '0;
            y     <= '0;
        end else begin
            case (state)
                IDLE: if (start) begin
                    xa <= a;
                    if (mem_size == '0) begin
                        y    <= a;
                        done <= 1'b1;
                    end else begin
                        m_req  <= 1'b1;
                        m_we   <= 1'b0;
                        m_addr <= mem_base + rd_off;
                        state  <= RD;
                    end
                end
                RD: if (m_ack) begin
                    d      <= m_rdata[17:0];
                    m_req  <= 1'b0;
                    state  <= WR;
                end
                WR: if (!m_req) begin
                    m_req   <= 1'b1;
                    m_we    <= 1'b1;
                    m_addr  <= mem_base + wpe;
                    m_wdata <= 32'(w);
                    y       <= sat18((38'(dry_a) + 38'(wet_d)) >>> 16);
                end else if (m_ack) begin
                    m_req <= 1'b0;
                    m_we  <= 1'b0;
                    wp    <= wpe + 1'b1 == mem_size ? '0 : wpe + 1'b1;
                    done  <= 1'b1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end

    wire unused = &{1'b0, b, m_rdata[31:18], p_wdata[31:AW]};

endmodule

`default_nettype wire
