// ST7789 display controller: SPI (mode 0) byte stream from a command FIFO, with
// accelerated fills and 1-bpp bitmap expansion (text) into RGB565 pixels.
// FIFO entry (register 0x00), bits [31:30] = type:
//   0: byte         {dc[8], data[7:0]}          dc = 0 command, 1 data
//   1: fill         count[23:0]                 count pixels of colour FG
//   2: bitmap       {nbits-1[20:16], bits[15:0]} MSB first, 1 -> FG, 0 -> BG
//   3: colour       {which[16], rgb565[15:0]}   which = 0: FG, 1: BG (in stream order)
// Registers: 0x00 FIFO (W)  0x04 STATUS R {busy[31], full[30], count[7:0]}
//            0x08 CTRL {bl[1], rst_n[0]}  0x0C FG  0x10 BG (RGB565)  0x14 DIV (SCK half period - 1)
// CS is low while the stream runs; pixels are sent big-endian.
`default_nettype none

module lcd_ctrl #(
    parameter int FIFO_DEPTH = 64,
    parameter int DIV_RST    = 1
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         req,
    input  wire         we,
    input  wire  [5:0]  addr,
    input  wire  [31:0] wdata,
    output logic [31:0] rdata,
    output logic        sck,
    output logic        mosi,
    output logic        cs_n,
    output logic        dc,
    output logic        rst_n,
    output logic        bl
);

    localparam int CW = $clog2(FIFO_DEPTH) + 1;

    logic [15:0] fg, bg;
    logic [7:0]  div;
    logic [31:0] q;
    logic        empty, full, pop;
    logic [CW-1:0] fcount;

    /* verilator lint_off PINCONNECTEMPTY */
    sync_fifo #(.WIDTH(32), .DEPTH(FIFO_DEPTH)) u_fifo (
        .clk(clk), .rst(rst), .wr_en(req && we && addr == 6'd0), .wr_data(wdata),
        .rd_en(pop), .rd_data(q), .empty(empty), .full(full), .count(fcount),
        .overflow(), .clr_overflow(1'b0)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // ------------------------------------------------ entry -> bytes expander
    logic [1:0]  kind;        // current entry type
    logic [23:0] left;        // pixels (fill) / bits (bitmap) left
    logic [15:0] bits;
    logic        lo;          // next byte is the low byte of a pixel
    logic        active;      // expanding an entry
    logic [8:0]  next_byte;   // {dc, byte}
    logic        have_byte;

    // byte shifter
    logic [7:0] sr;
    logic [3:0] nbit;
    logic [7:0] cnt;
    logic       shifting;

    wire [15:0] pix = (kind == 2'd1 || bits[15]) ? fg : bg;

    assign pop = !active && !empty && !have_byte;

    always_ff @(posedge clk) begin
        if (rst) begin
            active    <= 1'b0;
            have_byte <= 1'b0;
            lo        <= 1'b0;
        end else begin
            // take a new entry
            if (pop) begin
                kind <= q[31:30];
                case (q[31:30])
                    2'd0: begin
                        next_byte <= {q[8], q[7:0]};
                        have_byte <= 1'b1;
                    end
                    2'd1: begin
                        left   <= q[23:0];
                        active <= q[23:0] != '0;
                        lo     <= 1'b0;
                    end
                    2'd2: begin
                        left   <= {19'b0, q[20:16]} + 24'd1;
                        bits   <= q[15:0];
                        active <= 1'b1;
                        lo     <= 1'b0;
                    end
                    default: ;  // 3: colour, see the register block
                endcase
            end else if (active && !have_byte) begin
                have_byte <= 1'b1;
                if (!lo) begin
                    next_byte <= {1'b1, pix[15:8]};
                    lo        <= 1'b1;
                end else begin
                    next_byte <= {1'b1, pix[7:0]};
                    lo        <= 1'b0;
                    bits      <= {bits[14:0], 1'b0};
                    left      <= left - 24'd1;
                    if (left == 24'd1) active <= 1'b0;
                end
            end
            if (have_byte && !shifting) have_byte <= 1'b0;  // handed to the shifter below
        end
    end

    // SPI mode 0 shifter; CS stays low while bytes keep coming
    logic [7:0] idle_cnt;

    always_ff @(posedge clk) begin
        if (rst) begin
            shifting <= 1'b0;
            sck      <= 1'b0;
            mosi     <= 1'b0;
            cs_n     <= 1'b1;
            dc       <= 1'b0;
            cnt      <= '0;
            nbit     <= '0;
            idle_cnt <= '0;
        end else if (!shifting) begin
            if (have_byte) begin
                shifting <= 1'b1;
                cs_n     <= 1'b0;
                dc       <= next_byte[8];
                sr       <= {next_byte[6:0], 1'b0};
                mosi     <= next_byte[7];
                nbit     <= 4'd8;
                cnt      <= div;
                idle_cnt <= '0;
            end else if (!cs_n) begin
                // release CS after a short idle time with nothing to send
                if (idle_cnt == 8'd15) cs_n <= 1'b1;
                else                   idle_cnt <= idle_cnt + 8'd1;
            end
        end else if (cnt != '0) begin
            cnt <= cnt - 8'd1;
        end else begin
            cnt <= div;
            if (!sck) begin
                sck <= 1'b1;
            end else begin
                sck  <= 1'b0;
                nbit <= nbit - 4'd1;
                if (nbit == 4'd1) begin
                    shifting <= 1'b0;
                end else begin
                    mosi <= sr[7];
                    sr   <= {sr[6:0], 1'b0};
                end
            end
        end
    end

    // ------------------------------------------------------------ registers
    wire busy = !empty || active || have_byte || shifting;

    always_ff @(posedge clk) begin
        if (rst) begin
            fg    <= 16'hFFFF;
            bg    <= 16'h0000;
            div   <= 8'(DIV_RST);
            rst_n <= 1'b0;
            bl    <= 1'b0;
        end else if (pop && q[31:30] == 2'd3) begin
            if (q[16]) bg <= q[15:0];
            else       fg <= q[15:0];
        end else if (req && we) begin
            case (addr)
                6'd2: {bl, rst_n} <= wdata[1:0];
                6'd3: fg  <= wdata[15:0];
                6'd4: bg  <= wdata[15:0];
                6'd5: div <= wdata[7:0];
                default: ;
            endcase
        end
        if (req && !we) begin
            case (addr)
                6'd1:    rdata <= {busy, full, 22'b0, 8'(fcount)};
                6'd2:    rdata <= {30'b0, bl, rst_n};
                6'd3:    rdata <= {16'b0, fg};
                6'd4:    rdata <= {16'b0, bg};
                6'd5:    rdata <= {24'b0, div};
                default: rdata <= '0;
            endcase
        end
    end

    wire unused = &{1'b0, q[29:24], wdata[31:16]};

endmodule

`default_nettype wire
