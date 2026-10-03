// Timer. Registers:
//   0x00 CYCLES_LO  R: sys_clk cycle counter [31:0], latches [63:32]
//   0x04 CYCLES_HI  R: latched [63:32]
//   0x08 SAMPLES    R: audio_tick counter
`default_nettype none

module periph_timer (
    input  wire         clk,
    input  wire         rst,
    input  wire         req,
    input  wire         we,
    input  wire  [5:0]  addr,
    output logic [31:0] rdata,
    input  wire         audio_tick
);

    logic [63:0] cycles;
    logic [31:0] hi_latch, samples;

    always_ff @(posedge clk) begin
        if (rst) begin
            cycles   <= '0;
            samples  <= '0;
            hi_latch <= '0;
        end else begin
            cycles <= cycles + 64'd1;
            if (audio_tick) samples <= samples + 32'd1;
            if (req && !we && addr == 6'd0) hi_latch <= cycles[63:32];
        end
    end

    always_ff @(posedge clk) begin
        if (req && !we) begin
            case (addr)
                6'd0:    rdata <= cycles[31:0];
                6'd1:    rdata <= hi_latch;
                6'd2:    rdata <= samples;
                default: rdata <= '0;
            endcase
        end
    end

endmodule

`default_nettype wire
