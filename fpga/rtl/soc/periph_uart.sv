// Debug UART (BL702 USB bridge), 8N1 at BAUD. Registers (word offsets):
//   0x00 DATA   W: push TX byte (dropped if TX FIFO full)
//               R: pop RX byte: {valid[31], 23'b0, byte}
//   0x04 STATUS R: {rx_overflow[3], rx_avail[2], tx_idle[1], tx_full[0]}
//               W: bit3 = 1 clears rx_overflow
`default_nettype none

module periph_uart #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int BAUD       = 115_200,
    parameter int FIFO_DEPTH = 16
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         req,
    input  wire         we,
    input  wire  [5:0]  addr,
    input  wire  [31:0] wdata,
    output logic [31:0] rdata,
    input  wire         rx,
    output logic        tx
);

    localparam int DIV = (SYS_CLK_HZ + BAUD / 2) / BAUD;

    logic       wr_data, rd_data;
    logic [7:0] tx_q, rx_q, rx_byte;
    logic       tx_empty, tx_full, rx_empty, rx_ovf, rx_valid, tx_busy, tx_start;

    assign wr_data = req && we && addr == 6'd0;
    assign rd_data = req && !we && addr == 6'd0;

    /* verilator lint_off PINCONNECTEMPTY */
    sync_fifo #(.WIDTH(8), .DEPTH(FIFO_DEPTH)) u_txf (
        .clk(clk), .rst(rst), .wr_en(wr_data), .wr_data(wdata[7:0]),
        .rd_en(tx_start), .rd_data(tx_q), .empty(tx_empty), .full(tx_full),
        .count(), .overflow(), .clr_overflow(1'b0)
    );

    sync_fifo #(.WIDTH(8), .DEPTH(FIFO_DEPTH)) u_rxf (
        .clk(clk), .rst(rst), .wr_en(rx_valid), .wr_data(rx_byte),
        .rd_en(rd_data), .rd_data(rx_q), .empty(rx_empty), .full(),
        .count(), .overflow(rx_ovf), .clr_overflow(req && we && addr == 6'd1 && wdata[3])
    );
    /* verilator lint_on PINCONNECTEMPTY */

    assign tx_start = !tx_empty && !tx_busy;

    uart_tx u_tx (
        .clk(clk), .rst(rst), .div(16'(DIV)), .data(tx_q), .start(tx_start), .busy(tx_busy), .tx(tx)
    );

    uart_rx #(.SYS_CLK_HZ(SYS_CLK_HZ), .BAUD(BAUD)) u_rx (
        .clk(clk), .rst(rst), .rx(rx), .data(rx_byte), .valid(rx_valid)
    );

    always_ff @(posedge clk) begin
        if (req && !we) begin
            case (addr)
                6'd0:    rdata <= {!rx_empty, 23'b0, rx_q};
                6'd1:    rdata <= {28'b0, rx_ovf, !rx_empty, tx_empty && !tx_busy, tx_full};
                default: rdata <= '0;
            endcase
        end
    end

    wire unused = &{1'b0, wdata[31:8]};

endmodule

`default_nettype wire
