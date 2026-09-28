// SYNC input (AVK generator, after the comparator): glitch filter, rising edges, period.
// Registers (word offsets):
//   0x00 LEVEL (R) bit0          0x04 PERIOD (R) sys_clk cycles between the last two rising
//   edges (0 until two edges were seen, saturates)   0x08 EDGES (R) rising edge counter
//   0x0C FILTER  input must be stable this many sys_clk cycles (default 99 = 1 us at 99 MHz)
`default_nettype none

module sync_in (
    input  wire         clk,
    input  wire         rst,
    input  wire         tick,       // audio sample start
    input  wire         req,
    input  wire         we,
    input  wire  [5:0]  addr,
    input  wire  [31:0] wdata,
    output logic [31:0] rdata,
    input  wire         sync_pin,
    output logic        level,      // filtered
    output logic        edge_tick   // a rising edge happened in the previous sample period
);

    logic [2:0]  s;
    logic [15:0] filt, fcnt;
    logic        seen, pend;
    logic [31:0] since, period, edges;

    wire rise = !level && s[2] && fcnt == filt;

    always_ff @(posedge clk) begin
        s <= {s[1:0], sync_pin};
        if (rst) begin
            level     <= 1'b0;
            fcnt      <= '0;
            filt      <= 16'd99;
            seen      <= 1'b0;
            since     <= '0;
            period    <= '0;
            edges     <= '0;
            pend      <= 1'b0;
            edge_tick <= 1'b0;
        end else begin
            if (s[2] == level) begin
                fcnt <= '0;
            end else if (fcnt == filt) begin
                level <= s[2];
                fcnt  <= '0;
            end else begin
                fcnt <= fcnt + 16'd1;
            end
            if (since != '1) since <= since + 32'd1;
            if (rise) begin
                edges <= edges + 32'd1;
                since <= 32'd1;
                seen  <= 1'b1;
                if (seen) period <= since;
            end
            if (tick) begin
                edge_tick <= pend || rise;
                pend      <= 1'b0;
            end else if (rise) begin
                pend <= 1'b1;
            end
            if (req && we && addr == 6'd3) filt <= wdata[15:0];
        end
        if (req && !we) begin
            case (addr)
                6'd0: rdata <= {31'b0, level};
                6'd1: rdata <= period;
                6'd2: rdata <= edges;
                6'd3: rdata <= {16'b0, filt};
                default: rdata <= '0;
            endcase
        end
    end

    wire unused = &{1'b0, wdata[31:16]};

endmodule

`default_nettype wire
