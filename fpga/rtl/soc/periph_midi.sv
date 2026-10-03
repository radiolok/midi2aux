// MIDI input: UART 31250 -> parser -> event FIFO. Registers:
//   0x00 EVENT   R: pop {valid[31], 7'b0, status, d1, d2}
//   0x04 STATUS  R: {overflow[31], count[15:0]}
//   0x08 CTRL    W: bit0 = 1 clears overflow
`default_nettype none

module periph_midi #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int BAUD       = 31_250,
    parameter int FIFO_DEPTH = 64
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         req,
    input  wire         we,
    input  wire  [5:0]  addr,
    input  wire  [31:0] wdata,
    output logic [31:0] rdata,
    input  wire         midi_rx,
    output logic        activity  // 1 clk per event
);

    localparam int CW = $clog2(FIFO_DEPTH) + 1;

    logic [7:0]    rx_byte, st, d1, d2;
    logic          rx_valid, ev_valid, empty, ovf;
    logic [23:0]   ev;
    logic [CW-1:0] count;
    logic          pop;

    assign pop      = req && !we && addr == 6'd0;
    assign activity = ev_valid;

    uart_rx #(.SYS_CLK_HZ(SYS_CLK_HZ), .BAUD(BAUD)) u_rx (
        .clk(clk), .rst(rst), .rx(midi_rx), .data(rx_byte), .valid(rx_valid)
    );

    midi_parser u_parser (
        .clk(clk), .rst(rst), .in_data(rx_byte), .in_valid(rx_valid),
        .ev_status(st), .ev_d1(d1), .ev_d2(d2), .ev_valid(ev_valid)
    );

    /* verilator lint_off PINCONNECTEMPTY */
    sync_fifo #(.WIDTH(24), .DEPTH(FIFO_DEPTH)) u_fifo (
        .clk(clk), .rst(rst), .wr_en(ev_valid), .wr_data({st, d1, d2}),
        .rd_en(pop), .rd_data(ev), .empty(empty), .full(), .count(count),
        .overflow(ovf), .clr_overflow(req && we && addr == 6'd2 && wdata[0])
    );
    /* verilator lint_on PINCONNECTEMPTY */

    always_ff @(posedge clk) begin
        if (req && !we) begin
            case (addr)
                6'd0:    rdata <= {!empty, 7'b0, ev};
                6'd1:    rdata <= {ovf, 15'b0, 16'(count)};
                default: rdata <= '0;
            endcase
        end
    end

    wire unused = &{1'b0, wdata[31:1]};

endmodule

`default_nettype wire
