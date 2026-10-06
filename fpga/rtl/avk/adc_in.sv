// AVK inputs IN1 / IN2: two AD7091R SAR ADCs (shared CONVST, CS, SCLK; one SDO each) sampled
// OSR = 4 times per audio sample, calibrated to Q2.16 and decimated by a 64-tap FIR.
// ADC frame: CONVST low pulse, conversion time, CS low (MSB appears on SDO), 12 bits on SCLK
// rising edges. Model: fpga/model/synthmodel/avk.py (adc_to_q16, Decimator).
// Registers (word offsets):
//   0x00 OFFSET1  0x04 GAIN1  0x08 OFFSET2  0x0C GAIN2   x = sat18(((code - OFFSET) * GAIN) >> 16)
//   0x10 RAW1 (R) 0x14 RAW2 (R) last codes     0x18 IN1 (R) 0x1C IN2 (R) decimated, Q2.16
//   0x20 COUNT (R) completed output samples
`default_nettype none

module adc_in #(
    parameter int PERIOD     = 2048,  // sys_clk cycles per audio sample
    parameter int CONV_CYC   = 70,    // conversion time (AD7091R: 650 ns)
    parameter int SCLK_HALF  = 4      // SCLK half period, sys_clk cycles
) (
    input  wire                clk,
    input  wire                rst,
    input  wire                tick,     // audio sample start
    input  wire                req,
    input  wire                we,
    input  wire  [5:0]         addr,
    input  wire  [31:0]        wdata,
    output logic [31:0]        rdata,
    output logic               convst_n,
    output logic               cs_n,
    output logic               sclk,
    input  wire                sdo1,
    input  wire                sdo2,
    output logic signed [17:0] in1,      // updated once per sample
    output logic signed [17:0] in2
);

    localparam int OSR  = 4;
    localparam int SUB  = PERIOD / OSR;   // cycles between conversions
    localparam int TW   = $clog2(PERIOD);

    logic [11:0]        offs1, offs2, raw1, raw2;
    logic signed [31:0] gain1, gain2;
    logic [31:0]        count;

    always_ff @(posedge clk) begin
        if (rst) begin
            offs1 <= 12'd2048; offs2 <= 12'd2048;
            gain1 <= 32'sd2621440; gain2 <= 32'sd2621440;  // 40 << 16
        end else if (req && we) begin
            case (addr)
                6'd0: offs1 <= wdata[11:0];
                6'd1: gain1 <= wdata;
                6'd2: offs2 <= wdata[11:0];
                6'd3: gain2 <= wdata;
                default: ;
            endcase
        end
        if (req && !we) begin
            case (addr)
                6'd0: rdata <= 32'(offs1);
                6'd1: rdata <= gain1;
                6'd2: rdata <= 32'(offs2);
                6'd3: rdata <= gain2;
                6'd4: rdata <= 32'(raw1);
                6'd5: rdata <= 32'(raw2);
                6'd6: rdata <= 32'(in1);
                6'd7: rdata <= 32'(in2);
                6'd8: rdata <= count;
                default: rdata <= '0;
            endcase
        end
    end

    // ------------------------------------------------------------ ADC frames
    logic [TW-1:0] phase;       // position in the sample period
    logic [7:0]    cnt;
    logic [4:0]    nbit;
    logic [11:0]   sh1, sh2;
    typedef enum logic [2:0] {WAIT, CONV, READ, CAL, FIR} state_t;
    state_t        state;
    logic [1:0]    sub;          // conversion index within the sample
    logic          new_pair;

    always_ff @(posedge clk) begin
        if (rst || tick) phase <= '0;
        else             phase <= phase + 1'b1;
    end

    wire start_conv = (state == WAIT) && (phase == TW'(0) || phase == TW'(SUB) ||
                                          phase == TW'(2 * SUB) || phase == TW'(3 * SUB));

    always_ff @(posedge clk) begin
        new_pair <= 1'b0;
        if (rst) begin
            state    <= WAIT;
            convst_n <= 1'b1;
            cs_n     <= 1'b1;
            sclk     <= 1'b0;
            raw1     <= 12'd2048;
            raw2     <= 12'd2048;
            sub      <= '0;
        end else case (state)
            WAIT: if (start_conv) begin
                convst_n <= 1'b0;
                cnt      <= 8'(CONV_CYC);
                sub      <= phase == TW'(0) ? 2'd0 : sub + 2'd1;
                state    <= CONV;
            end
            CONV: begin
                if (cnt == 8'(CONV_CYC - 2)) convst_n <= 1'b1;  // 20 ns pulse
                if (cnt == '0) begin
                    cs_n  <= 1'b0;
                    nbit  <= 5'd12;
                    cnt   <= 8'(SCLK_HALF - 1);
                    state <= READ;
                end else begin
                    cnt <= cnt - 8'd1;
                end
            end
            READ: if (cnt != '0) begin
                cnt <= cnt - 8'd1;
            end else begin
                cnt <= 8'(SCLK_HALF - 1);
                if (!sclk) begin
                    sclk <= 1'b1;
                    sh1  <= {sh1[10:0], sdo1};
                    sh2  <= {sh2[10:0], sdo2};
                end else begin
                    sclk <= 1'b0;
                    nbit <= nbit - 5'd1;
                    if (nbit == 5'd1) begin
                        cs_n     <= 1'b1;
                        raw1     <= sh1;
                        raw2     <= sh2;
                        new_pair <= 1'b1;
                        state    <= WAIT;
                    end
                end
            end
            default: state <= WAIT;
        endcase
    end

    // ------------------------------------------------------------- calibration + FIR
    // history RAMs (64 x 18 per channel), newest at wp
    logic signed [17:0] h1 [64];
    logic signed [17:0] h2 [64];
    logic [5:0]         wp, tap;
    logic signed [17:0] x1, x2, c;
    logic signed [17:0] rd1, rd2;
    logic signed [42:0] acc1, acc2;
    logic [1:0]         fstate;   // 0 idle, 1 calibrate/write, 2 MAC
    logic [6:0]         mac;
    logic               do_fir;
    logic [17:0]        rom_q;

    function automatic logic signed [17:0] cal(input logic [11:0] code, input logic [11:0] off,
                                               input logic signed [31:0] g);
        logic signed [45:0] p;
        p = (46'($signed({1'b0, code})) - 46'($signed({1'b0, off}))) * 46'(g);
        if ((p >>> 16) > 46'sd131071) return 18'sd131071;
        if ((p >>> 16) < -46'sd131072) return -18'sd131072;
        return 18'(p >>> 16);
    endfunction

    fir_rom u_coef (.clk(clk), .addr(tap), .data(rom_q));
    assign c = rom_q;

    always_ff @(posedge clk) begin
        rd1 <= h1[wp - tap];
        rd2 <= h2[wp - tap];
    end

    // MAC pipeline: tap issued at mac = n, coefficient and samples ready one clk later
    always_ff @(posedge clk) begin
        if (rst) begin
            wp     <= '0;
            fstate <= '0;
            in1    <= '0;
            in2    <= '0;
            count  <= '0;
            for (int n = 0; n < 64; n++) begin
                h1[n] <= '0;
                h2[n] <= '0;
            end
        end else case (fstate)
            2'd0: if (new_pair) begin
                x1     <= cal(raw1, offs1, gain1);  // raw registers were loaded with new_pair
                x2     <= cal(raw2, offs2, gain2);
                do_fir <= sub == 2'd3;
                fstate <= 2'd1;
            end
            2'd1: begin
                h1[wp + 6'd1] <= x1;
                h2[wp + 6'd1] <= x2;
                wp            <= wp + 6'd1;
                if (do_fir) begin
                    tap    <= '0;
                    mac    <= '0;
                    acc1   <= '0;
                    acc2   <= '0;
                    fstate <= 2'd2;
                end else begin
                    fstate <= 2'd0;
                end
            end
            2'd2: begin
                if (mac != '0) begin  // data of tap mac-1
                    acc1 <= acc1 + 43'(c * rd1);
                    acc2 <= acc2 + 43'(c * rd2);
                end
                tap <= tap + 6'd1;
                mac <= mac + 7'd1;
                if (mac == 7'd64) begin
                    in1    <= sat18q(acc1 + 43'(c * rd1));
                    in2    <= sat18q(acc2 + 43'(c * rd2));
                    count  <= count + 32'd1;
                    fstate <= 2'd0;
                end
            end
            default: fstate <= 2'd0;
        endcase
    end

    function automatic logic signed [17:0] sat18q(input logic signed [42:0] a);
        if ((a >>> 17) > 43'sd131071) return 18'sd131071;
        if ((a >>> 17) < -43'sd131072) return -18'sd131072;
        return 18'(a >>> 17);
    endfunction

    wire unused = &{1'b0, wdata[31:12]};

endmodule

`default_nettype wire
