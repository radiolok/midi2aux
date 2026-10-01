// Slot MATH (TYPE_ID 1): operations on two bus signals, like the AVK's math blocks.
// PARAM0 = op: 0 A*B  1 A/B  2 |A|  3 A+B  4 A-B  5 min  6 max  7 A mod B  8 A*k+B;
// PARAM1 = k (Q2.16). All results saturated to 18 bit. A/B and A mod B take ~36 clk.
// Model: fpga/model/synthmodel/avk.py (math_op).
//
// Standard slot interface: start (a, b valid) -> done (y valid), parameter write port.
`default_nettype none

module slot_math (
    input  wire                clk,
    input  wire                rst,
    input  wire                start,
    input  wire signed [17:0]  a,
    input  wire signed [17:0]  b,
    input  wire                p_we,
    input  wire  [3:0]         p_addr,
    input  wire  [31:0]        p_wdata,
    output logic signed [17:0] y,
    output logic               done
);

    localparam logic signed [17:0] MAXV = 18'sd131071, MINV = -18'sd131072;

    logic [3:0]         op;
    logic signed [17:0] k;

    always_ff @(posedge clk) begin
        if (rst) begin
            op <= '0;
            k  <= '0;
        end else if (p_we) begin
            if (p_addr == 4'd0) op <= p_wdata[3:0];
            if (p_addr == 4'd1) k  <= p_wdata[17:0];
        end
    end

    function automatic logic signed [17:0] sat18(input logic signed [36:0] x);
        if (x > 37'(MAXV)) return MAXV;
        if (x < 37'(MINV)) return MINV;
        return x[17:0];
    endfunction

    // restoring divider on magnitudes: 34-bit dividend (|a| << 16 or |a|), 17-bit divisor
    logic [33:0] num, quo;
    logic [17:0] rem;
    logic [5:0]  cnt;
    logic        busy, neg_q, neg_r, is_mod;
    logic signed [17:0] a_q, b_q;

    wire [17:0] a_mag = a[17] ? 18'(-a) : 18'(a);
    wire [17:0] b_mag = b[17] ? 18'(-b) : 18'(b);
    wire [18:0] trial = {rem, num[33]} - {1'b0, b_q[17] ? 18'(-b_q) : 18'(b_q)};

    wire signed [17:0] mb   = op == 4'd8 ? k : b;
    wire signed [35:0] prod = a * mb;

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            busy <= 1'b0;
            y    <= '0;
        end else if (start) begin
            a_q <= a;
            b_q <= b;
            case (op)
                4'd0: begin y <= sat18(37'(prod) >>> 16); done <= 1'b1; end
                4'd2: begin y <= sat18(a[17] ? -37'(a) : 37'(a)); done <= 1'b1; end
                4'd3: begin y <= sat18(37'(a) + 37'(b)); done <= 1'b1; end
                4'd4: begin y <= sat18(37'(a) - 37'(b)); done <= 1'b1; end
                4'd5: begin y <= a < b ? a : b; done <= 1'b1; end
                4'd6: begin y <= a > b ? a : b; done <= 1'b1; end
                4'd8: begin y <= sat18((37'(prod) >>> 16) + 37'(b)); done <= 1'b1; end
                4'd1, 4'd7: begin
                    if (b == 0) begin
                        y    <= op == 4'd7 ? a : (a[17] ? MINV : MAXV);
                        done <= 1'b1;
                    end else begin
                        busy   <= 1'b1;
                        is_mod <= op == 4'd7;
                        num    <= op == 4'd7 ? {16'b0, a_mag} : {a_mag, 16'b0};
                        rem    <= '0;
                        quo    <= '0;
                        cnt    <= 6'd34;
                        neg_q  <= a[17] ^ b[17];
                        neg_r  <= a[17];
                    end
                end
                default: begin y <= a; done <= 1'b1; end
            endcase
        end else if (busy) begin
            if (cnt != 6'd0) begin
                // shift in the next dividend bit, subtract the divisor if it fits
                if (!trial[18]) begin
                    rem <= trial[17:0];
                    quo <= {quo[32:0], 1'b1};
                end else begin
                    rem <= {rem[16:0], num[33]};
                    quo <= {quo[32:0], 1'b0};
                end
                num <= {num[32:0], 1'b0};
                cnt <= cnt - 6'd1;
            end else begin
                busy <= 1'b0;
                done <= 1'b1;
                if (is_mod)
                    y <= neg_r ? -$signed(rem) : $signed(rem);
                else if (neg_q)
                    y <= quo > 34'd131072 ? MINV : -$signed(quo[17:0]);
                else
                    y <= quo > 34'd131071 ? MAXV : $signed(quo[17:0]);
            end
        end
    end

    wire unused = &{1'b0, p_wdata[31:18], a_q, b_mag};

endmodule

`default_nettype wire
