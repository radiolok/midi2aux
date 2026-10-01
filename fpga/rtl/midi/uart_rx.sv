// UART receiver 8N1 (MIDI: 31250 baud). Samples each bit in its middle;
// a byte with a bad stop bit is dropped.
`default_nettype none

module uart_rx #(
    parameter int SYS_CLK_HZ = 99_000_000,
    parameter int BAUD       = 31_250
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        rx,
    output logic [7:0] data,
    output logic       valid
);

    localparam int DIV = (SYS_CLK_HZ + BAUD / 2) / BAUD;
    localparam int CW  = $clog2(DIV);

    typedef enum logic [1:0] {IDLE, START, DATA, STOP} state_t;

    state_t        state;
    logic [2:0]    rx_sync;
    logic [CW-1:0] cnt;
    logic [2:0]    bit_idx;
    logic [7:0]    sr;
    logic          rx_s;

    assign rx_s = rx_sync[2];

    always_ff @(posedge clk) begin
        if (rst) rx_sync <= 3'b111;
        else     rx_sync <= {rx_sync[1:0], rx};
    end

    always_ff @(posedge clk) begin
        valid <= 1'b0;
        if (rst) begin
            state   <= IDLE;
            cnt     <= '0;
            bit_idx <= '0;
            sr      <= '0;
            data    <= '0;
        end else begin
            case (state)
                IDLE: if (!rx_s) begin
                    state <= START;
                    cnt   <= CW'(DIV / 2 - 1);
                end
                START: if (cnt == '0) begin
                    // middle of the start bit: still low -> real start
                    state   <= rx_s ? IDLE : DATA;
                    cnt     <= CW'(DIV - 1);
                    bit_idx <= '0;
                end else begin
                    cnt <= cnt - CW'(1);
                end
                DATA: if (cnt == '0) begin
                    sr      <= {rx_s, sr[7:1]};  // LSB first
                    cnt     <= CW'(DIV - 1);
                    bit_idx <= bit_idx + 3'd1;
                    if (bit_idx == 3'd7)
                        state <= STOP;
                end else begin
                    cnt <= cnt - CW'(1);
                end
                STOP: if (cnt == '0) begin
                    state <= IDLE;
                    if (rx_s) begin
                        data  <= sr;
                        valid <= 1'b1;
                    end
                end else begin
                    cnt <= cnt - CW'(1);
                end
                default: state <= IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
