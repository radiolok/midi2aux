// Slot CHORUS (TYPE_ID 3): modulated delay line in external memory (chorus, flanger).
// Triangle LFO tri = phase[30:15] (inverted when phase[31]); delay = BASE + DEPTH * tri / 2^16
// samples (integer part clamped to MEM_SIZE - 2), linear interpolation of two taps:
//   d = r0 + ((r1 - r0) * frac >> 16); mem[wp] = sat18(A + FB * d); y = sat18(DRY * A + WET * d).
// PARAM0 BASE  PARAM1 DEPTH (samples)  PARAM2 RATE (phase increment)  PARAM3 FB  PARAM4 WET
// PARAM5 DRY (Q2.16). MEM_SIZE < 2: y = A. Model: fpga/model/synthmodel/avk.py (Slot.chorus).
`default_nettype none

module slot_chorus #(
    parameter int AW = 24
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

    logic [23:0]        base, depth;
    logic [31:0]        rate, ph;
    logic signed [17:0] fb, wet, dry, xa, r0, r1;
    logic [AW-1:0]      wp;

    always_ff @(posedge clk) begin
        if (rst) begin
            base  <= '0;
            depth <= '0;
            rate  <= '0;
            fb    <= '0;
            wet   <= '0;
            dry   <= 18'sd65536;
        end else if (p_we) begin
            case (p_addr)
                4'd0: base  <= p_wdata[23:0];
                4'd1: depth <= p_wdata[23:0];
                4'd2: rate  <= p_wdata;
                4'd3: fb    <= p_wdata[17:0];
                4'd4: wet   <= p_wdata[17:0];
                4'd5: dry   <= p_wdata[17:0];
                default: ;
            endcase
        end
    end

    function automatic logic signed [17:0] sat18(input logic signed [39:0] x);
        if (x > 40'(MAXV)) return MAXV;
        if (x < 40'(MINV)) return MINV;
        return x[17:0];
    endfunction

    wire [15:0]   tri_v = ph[31] ? ~ph[30:15] : ph[30:15];
    wire [39:0]   off   = {base, 16'b0} + 40'(depth) * 40'(tri_v);
    wire [AW-1:0] imax  = mem_size - AW'(2);
    wire [AW-1:0] i     = off[39:16] > 24'(imax) ? imax : AW'(off[39:16]);
    wire [AW-1:0] wpe   = wp >= mem_size ? '0 : wp;
    wire [AW-1:0] o0    = wpe >= i ? wpe - i : wpe + mem_size - i;          // wp - i
    wire [AW-1:0] o1    = o0 == '0 ? mem_size - 1'b1 : o0 - 1'b1;          // wp - i - 1
    logic [15:0]  fr;

    wire signed [18:0] diff  = 19'(r1) - 19'(r0);
    wire signed [35:0] dprod = diff * $signed({1'b0, fr});
    wire signed [17:0] d     = sat18(40'(r0) + (40'(dprod) >>> 16));  // never saturates
    wire signed [35:0] fb_d  = fb * d;
    wire signed [35:0] dry_a = dry * xa;
    wire signed [35:0] wet_d = wet * d;

    typedef enum logic [2:0] {IDLE, RD0, RD1, WR} state_t;
    state_t state;
    logic [AW-1:0] a1;

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            state <= IDLE;
            m_req <= 1'b0;
            m_we  <= 1'b0;
            wp    <= '0;
            ph    <= '0;
            y     <= '0;
        end else begin
            case (state)
                IDLE: if (start) begin
                    xa <= a;
                    if (mem_size < AW'(2)) begin
                        y    <= a;
                        done <= 1'b1;
                    end else begin
                        fr     <= off[15:0];
                        a1     <= mem_base + o1;
                        m_req  <= 1'b1;
                        m_we   <= 1'b0;
                        m_addr <= mem_base + o0;
                        state  <= RD0;
                    end
                end
                RD0: if (m_ack) begin
                    r0    <= m_rdata[17:0];
                    m_req <= 1'b0;
                    state <= RD1;
                end
                RD1: if (!m_req) begin
                    m_req  <= 1'b1;
                    m_addr <= a1;
                end else if (m_ack) begin
                    r1    <= m_rdata[17:0];
                    m_req <= 1'b0;
                    state <= WR;
                end
                WR: if (!m_req) begin
                    m_req   <= 1'b1;
                    m_we    <= 1'b1;
                    m_addr  <= mem_base + wpe;
                    m_wdata <= 32'(sat18(40'(xa) + (40'(fb_d) >>> 16)));
                    y       <= sat18((40'(dry_a) + 40'(wet_d)) >>> 16);
                end else if (m_ack) begin
                    m_req <= 1'b0;
                    m_we  <= 1'b0;
                    wp    <= wpe + 1'b1 == mem_size ? '0 : wpe + 1'b1;
                    ph    <= ph + rate;
                    done  <= 1'b1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end

    wire unused = &{1'b0, b, m_rdata[31:18], p_wdata[31:24]};

endmodule

`default_nettype wire
