// MCP3208 poller: scans the 8 potentiometer channels continuously over SPI (mode 0),
// one 24-clock frame per channel: {5'b0, start, single-ended, D2 D1 D0, 14'b0}; the result
// is the last 12 bits received. Each channel is smoothed: s += ((raw << 4) - s) >> SMOOTH;
// the first conversion after reset sets s = raw << 4 (no start-up ramp that looks like a turn).
// Registers (word offsets):
//   0x00..0x1C  POT0..POT7  R: smoothed value, 16 bit (12.4)
//   0x20..0x3C  RAW0..RAW7  R: last conversion, 12 bit
//   0x40        SCANS       R: completed scans of all 8 channels
`default_nettype none

module periph_pots #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int SPI_HZ     = 1_000_000,
    parameter int SMOOTH     = 3
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         req,
    input  wire         we,
    input  wire  [5:0]  addr,
    output logic [31:0] rdata,
    output logic        sck,
    output logic        mosi,
    input  wire         miso,
    output logic        cs_n
);

    localparam int HALF = (SYS_CLK_HZ + 2 * SPI_HZ - 1) / (2 * SPI_HZ);  // clk per SCK half period
    localparam int CW   = $clog2(HALF + 1);

    logic [CW-1:0] cnt;
    logic [4:0]    nbit;     // bits left in the frame
    logic [2:0]    ch;
    logic [23:0]   tx;
    logic [11:0]   rx;       // last 12 bits received = the conversion result
    logic [1:0]    gap;      // CS high time between frames, in half periods
    logic [11:0]   raw [8];
    logic [15:0]   pot [8];
    logic [31:0]   scans;
    logic          seeded;   // first scan done

    wire [23:0] frame = {5'b00000, 1'b1, 1'b1, ch, 14'b0};

    always_ff @(posedge clk) begin
        if (rst) begin
            cnt   <= '0;
            nbit  <= '0;
            ch    <= '0;
            sck   <= 1'b0;
            mosi  <= 1'b0;
            cs_n  <= 1'b1;
            gap   <= 2'd3;
            scans <= '0;
            seeded <= 1'b0;
            for (int i = 0; i < 8; i++) begin
                raw[i] <= '0;
                pot[i] <= '0;
            end
        end else if (cnt != '0) begin
            cnt <= cnt - 1'b1;
        end else begin
            cnt <= CW'(HALF - 1);
            if (cs_n) begin
                if (gap != '0) begin
                    gap <= gap - 2'd1;
                end else begin  // start a frame: first bit on MOSI before the first rising edge
                    cs_n <= 1'b0;
                    tx   <= {frame[22:0], 1'b0};
                    mosi <= frame[23];
                    nbit <= 5'd24;
                end
            end else if (!sck) begin  // rising edge: sample MISO
                sck <= 1'b1;
                rx  <= {rx[10:0], miso};
            end else begin            // falling edge: next bit or end of frame
                sck  <= 1'b0;
                nbit <= nbit - 5'd1;
                if (nbit == 5'd1) begin
                    cs_n    <= 1'b1;
                    gap     <= 2'd3;
                    raw[ch] <= rx[11:0];
                    if (!seeded) pot[ch] <= {rx[11:0], 4'b0};
                    else pot[ch] <= pot[ch] + 16'(($signed({1'b0, rx[11:0], 4'b0}) - $signed({1'b0, pot[ch]})) >>> SMOOTH);
                    ch      <= ch + 3'd1;
                    if (ch == 3'd7) begin
                        scans  <= scans + 32'd1;
                        seeded <= 1'b1;
                    end
                end else begin
                    mosi <= tx[23];
                    tx   <= {tx[22:0], 1'b0};
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (req && !we) begin
            if (addr[5:3] == 3'd0)      rdata <= {16'b0, pot[addr[2:0]]};
            else if (addr[5:3] == 3'd1) rdata <= {20'b0, raw[addr[2:0]]};
            else if (addr == 6'd16)     rdata <= scans;
            else                        rdata <= '0;
        end
    end

endmodule

`default_nettype wire
