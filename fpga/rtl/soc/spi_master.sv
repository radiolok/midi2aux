// SPI master, mode 0 (CPOL = 0, CPHA = 0), MSB first, byte transfers.
// SCK half period = div + 1 sys_clk cycles. Registers:
//   0x00 DATA   W: start a transfer of wdata[7:0]; R: last received byte
//   0x04 STATUS R: bit0 busy
//   0x08 CS     R/W: selected devices (cs_n = ~CS)
//   0x0C DIV    R/W: SCK half period - 1
`default_nettype none

module spi_master #(
    parameter int NCS     = 1,
    parameter int DIV_RST = 1
) (
    input  wire            clk,
    input  wire            rst,
    input  wire            req,
    input  wire            we,
    input  wire  [5:0]     addr,
    input  wire  [31:0]    wdata,
    output logic [31:0]    rdata,
    output logic           sck,
    output logic           mosi,
    input  wire            miso,
    output logic [NCS-1:0] cs_n
);

    logic [7:0]     div, cnt, sr, rx;
    logic [3:0]     nbit;
    logic           busy;
    logic [NCS-1:0] cs;

    assign cs_n = ~cs;

    always_ff @(posedge clk) begin
        if (rst) begin
            div  <= 8'(DIV_RST);
            cs   <= '0;
            busy <= 1'b0;
            sck  <= 1'b0;
            mosi <= 1'b0;
            cnt  <= '0;
            nbit <= '0;
            sr   <= '0;
            rx   <= '0;
        end else begin
            if (req && we) begin
                case (addr)
                    6'd0: if (!busy) begin
                        busy <= 1'b1;
                        sr   <= wdata[7:0];
                        mosi <= wdata[7];
                        nbit <= 4'd8;
                        cnt  <= div;
                    end
                    6'd2: cs  <= wdata[NCS-1:0];
                    6'd3: div <= wdata[7:0];
                    default: ;
                endcase
            end
            if (busy) begin
                if (cnt != '0) begin
                    cnt <= cnt - 8'd1;
                end else begin
                    cnt <= div;
                    if (!sck) begin           // rising edge: sample
                        sck <= 1'b1;
                        sr  <= {sr[6:0], miso};
                    end else begin            // falling edge: shift out next bit
                        sck  <= 1'b0;
                        nbit <= nbit - 4'd1;
                        mosi <= sr[7];
                        if (nbit == 4'd1) begin
                            busy <= 1'b0;
                            rx   <= sr;
                        end
                    end
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (req && !we) begin
            case (addr)
                6'd0:    rdata <= {24'b0, rx};
                6'd1:    rdata <= {31'b0, busy};
                6'd2:    rdata <= 32'(cs);
                6'd3:    rdata <= {24'b0, div};
                default: rdata <= '0;
            endcase
        end
    end

    wire unused = &{1'b0, wdata[31:8]};

endmodule

`default_nettype wire
