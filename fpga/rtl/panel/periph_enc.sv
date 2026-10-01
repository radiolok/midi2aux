// Rotary encoders (EC11) with push buttons: debounce, quadrature decode, detent counters.
// Inputs are active low (pull-ups, contacts to ground). Registers (word offsets):
//   0x00..0x0C  COUNT0..COUNT3  R: signed detent count (16 bit); W: any value clears it
//   0x10        BUTTONS         R: current state, bit k = button k pressed
//   0x14        PRESSED         R: press events since the last clear; W: 1 clears the bit
`default_nettype none

module periph_enc #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int N          = 4,
    parameter int DEBOUNCE_US = 200,  // input must be stable this long
    parameter int STEPS      = 4      // quadrature transitions per detent (EC11: 4 or 2)
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         req,
    input  wire         we,
    input  wire  [5:0]  addr,
    input  wire  [31:0] wdata,
    output logic [31:0] rdata,
    input  wire [N-1:0] enc_a,   // active low
    input  wire [N-1:0] enc_b,
    input  wire [N-1:0] enc_sw
);

    localparam int DEB = SYS_CLK_HZ / 1_000_000 * DEBOUNCE_US;
    localparam int DW  = $clog2(DEB + 1);

    // one debouncer per input: 3 * N signals
    logic [3*N-1:0] in_s1, in_s2, stable;
    logic [DW-1:0]  deb_cnt [3*N];

    wire [3*N-1:0] raw = ~{enc_sw, enc_b, enc_a};

    always_ff @(posedge clk) begin
        in_s1 <= raw;
        in_s2 <= in_s1;
        for (int i = 0; i < 3 * N; i++) begin
            if (rst) begin
                stable[i]  <= 1'b0;
                deb_cnt[i] <= '0;
            end else if (in_s2[i] == stable[i]) begin
                deb_cnt[i] <= '0;
            end else if (deb_cnt[i] == DW'(DEB)) begin
                stable[i]  <= in_s2[i];
                deb_cnt[i] <= '0;
            end else begin
                deb_cnt[i] <= deb_cnt[i] + 1'b1;
            end
        end
    end

    wire [N-1:0] a  = stable[N-1:0];
    wire [N-1:0] b  = stable[2*N-1:N];
    wire [N-1:0] sw = stable[3*N-1:2*N];

    logic [N-1:0]       a_q, b_q, sw_q, pressed;
    logic signed [3:0]  sub [N];
    logic signed [15:0] count [N];

    always_ff @(posedge clk) begin
        if (rst) begin
            a_q     <= '0;
            b_q     <= '0;
            sw_q    <= '0;
            pressed <= '0;
            for (int k = 0; k < N; k++) begin
                sub[k]   <= '0;
                count[k] <= '0;
            end
        end else begin
            a_q  <= a;
            b_q  <= b;
            sw_q <= sw;
            for (int k = 0; k < N; k++) begin
                // Gray code step: +1 clockwise (A leads B), -1 counter-clockwise
                logic signed [3:0] d;
                d = 4'sd0;
                if (a[k] != a_q[k] && b[k] == b_q[k]) d = (a[k] != b[k]) ? 4'sd1 : -4'sd1;
                if (b[k] != b_q[k] && a[k] == a_q[k]) d = (a[k] == b[k]) ? 4'sd1 : -4'sd1;
                if (req && we && addr == 6'(k)) begin
                    count[k] <= '0;
                    sub[k]   <= '0;
                end else if (sub[k] + d == 4'(STEPS)) begin
                    count[k] <= count[k] + 16'sd1;
                    sub[k]   <= '0;
                end else if (sub[k] + d == -4'(STEPS)) begin
                    count[k] <= count[k] - 16'sd1;
                    sub[k]   <= '0;
                end else begin
                    sub[k] <= sub[k] + d;
                end
                if (sw[k] && !sw_q[k]) pressed[k] <= 1'b1;
                else if (req && we && addr == 6'd5 && wdata[k]) pressed[k] <= 1'b0;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (req && !we) begin
            if (addr < 6'(N))      rdata <= 32'(count[addr[1:0]]);
            else if (addr == 6'd4) rdata <= 32'(sw);
            else if (addr == 6'd5) rdata <= 32'(pressed);
            else                   rdata <= '0;
        end
    end

endmodule

`default_nettype wire
