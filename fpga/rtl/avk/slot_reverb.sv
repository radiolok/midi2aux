// Slot REVERB (TYPE_ID 4): Schroeder / Freeverb structure in external memory: 4 parallel comb
// filters with a one-pole lowpass in the loop, then 2 allpasses (feedback 1/2). Buffers of
// 1116, 1188, 1277, 1356, 556, 441 words follow each other from MEM_BASE (5934 words; less
// MEM_SIZE: y = A). Per sample, x = A >>> 2, acc = 0; comb k: o = buf[p]; filt = sat18((o * (1 - DAMP)
// + filt * DAMP) >> 16); buf[p] = sat18(x + (filt * ROOM >> 16)); acc += o (sat18 after the 4th);
// allpass: o = buf[p]; buf[p] = sat18(acc + (o >>> 1)); acc = sat18(o - acc).
// y = sat18((DRY * A + WET * acc) >> 16).
// PARAM0 ROOM (Q2.16)  PARAM1 DAMP (0..65535, Q16)  PARAM2 WET  PARAM3 DRY (Q2.16).
// Model: fpga/model/synthmodel/avk.py (Slot.reverb).
`default_nettype none

module slot_reverb #(
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
    localparam int TOTAL = 5934;

    function automatic logic [12:0] len(input logic [2:0] k);
        case (k)
            3'd0: return 13'd1116;
            3'd1: return 13'd1188;
            3'd2: return 13'd1277;
            3'd3: return 13'd1356;
            3'd4: return 13'd556;
            default: return 13'd441;
        endcase
    endfunction

    function automatic logic [12:0] start_of(input logic [2:0] k);
        case (k)
            3'd0: return 13'd0;
            3'd1: return 13'd1116;
            3'd2: return 13'd2304;
            3'd3: return 13'd3581;
            3'd4: return 13'd4937;
            default: return 13'd5493;
        endcase
    endfunction

    function automatic logic signed [17:0] sat18(input logic signed [39:0] x);
        if (x > 40'(MAXV)) return MAXV;
        if (x < 40'(MINV)) return MINV;
        return x[17:0];
    endfunction

    logic signed [17:0] room, wet, dry;
    logic [15:0]        damp;

    always_ff @(posedge clk) begin
        if (rst) begin
            room <= '0;
            damp <= '0;
            wet  <= '0;
            dry  <= 18'sd65536;
        end else if (p_we) begin
            case (p_addr)
                4'd0: room <= p_wdata[17:0];
                4'd1: damp <= p_wdata[15:0];
                4'd2: wet  <= p_wdata[17:0];
                4'd3: dry  <= p_wdata[17:0];
                default: ;
            endcase
        end
    end

    logic [12:0]        p [6];
    logic signed [17:0] filt [4];
    logic signed [17:0] xa, x, o;
    logic signed [19:0] acc;   // 4 comb outputs
    logic [2:0]         k;

    wire signed [17:0] fk      = filt[k[1:0]];
    wire signed [35:0] o_nd    = o * $signed({1'b0, 17'd65536 - 17'(damp)});
    wire signed [35:0] f_d     = fk * $signed({2'b0, damp});
    wire signed [17:0] f_new   = sat18((40'(o_nd) + 40'(f_d)) >>> 16);
    wire signed [35:0] f_room  = f_new * room;
    wire signed [17:0] comb_w  = sat18(40'(x) + (40'(f_room) >>> 16));
    wire signed [19:0] acc_c   = acc + 20'(o);
    wire signed [17:0] acc18   = acc[17:0];
    wire signed [17:0] ap_w    = sat18(40'(acc18) + (40'(o) >>> 1));
    wire signed [17:0] ap_out  = sat18(40'(o) - 40'(acc18));
    wire signed [35:0] dry_a   = dry * xa;
    wire signed [35:0] wet_acc = wet * acc18;

    typedef enum logic [2:0] {IDLE, RD, WR, NEXT, FIN} state_t;
    state_t state;

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            state <= IDLE;
            m_req <= 1'b0;
            m_we  <= 1'b0;
            y     <= '0;
            for (int n = 0; n < 6; n++) p[n] <= '0;
            for (int n = 0; n < 4; n++) filt[n] <= '0;
        end else begin
            case (state)
                IDLE: if (start) begin
                    xa <= a;
                    if (mem_size < AW'(TOTAL)) begin
                        y    <= a;
                        done <= 1'b1;
                    end else begin
                        x     <= a >>> 2;
                        acc   <= '0;
                        k     <= '0;
                        state <= NEXT;
                    end
                end
                NEXT: begin  // read buffer k
                    m_req  <= 1'b1;
                    m_we   <= 1'b0;
                    m_addr <= mem_base + AW'(start_of(k)) + AW'(p[k]);
                    state  <= RD;
                end
                RD: if (m_ack) begin
                    o     <= m_rdata[17:0];
                    m_req <= 1'b0;
                    state <= WR;
                end
                WR: if (!m_req) begin
                    m_req <= 1'b1;
                    m_we  <= 1'b1;
                    if (k < 3'd4) begin
                        filt[k[1:0]] <= f_new;
                        m_wdata      <= 32'(comb_w);
                        // saturate the comb sum to 18 bits after the 4th comb
                        acc <= k == 3'd3 ? 20'(sat18(40'(acc_c))) : acc_c;
                    end else begin
                        m_wdata <= 32'(ap_w);
                        acc     <= 20'(ap_out);
                    end
                end else if (m_ack) begin
                    m_req <= 1'b0;
                    m_we  <= 1'b0;
                    p[k]  <= p[k] + 1'b1 == len(k) ? '0 : p[k] + 1'b1;
                    k     <= k + 1'b1;
                    state <= k == 3'd5 ? FIN : NEXT;
                end
                FIN: begin
                    y     <= sat18((40'(dry_a) + 40'(wet_acc)) >>> 16);
                    done  <= 1'b1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end

    wire unused = &{1'b0, b, m_rdata[31:18], p_wdata[31:18], acc[19:18]};

endmodule

`default_nettype wire
