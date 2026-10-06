// UART transmitter 8N1, bit period = div sys_clk cycles (runtime).
`default_nettype none

module uart_tx (
    input  wire        clk,
    input  wire        rst,
    input  wire [15:0] div,    // clk per bit, >= 2
    input  wire [7:0]  data,
    input  wire        start,  // ignored while busy
    output logic       busy,
    output logic       tx
);

    logic [15:0] cnt;
    logic [3:0]  nbit;
    logic [8:0]  sr;  // {stop, data} shifted out after the start bit

    always_ff @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0;
            tx   <= 1'b1;
            cnt  <= '0;
            nbit <= '0;
            sr   <= '1;
        end else if (!busy) begin
            if (start) begin
                busy <= 1'b1;
                tx   <= 1'b0;
                sr   <= {1'b1, data};
                cnt  <= div - 16'd1;
                nbit <= 4'd9;
            end
        end else if (cnt != '0) begin
            cnt <= cnt - 16'd1;
        end else if (nbit != '0) begin
            tx   <= sr[0];
            sr   <= {1'b1, sr[8:1]};
            nbit <= nbit - 4'd1;
            cnt  <= div - 16'd1;
        end else begin
            busy <= 1'b0;  // stop bit done
        end
    end

endmodule

`default_nettype wire
