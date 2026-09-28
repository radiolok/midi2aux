// GPIO. Registers: 0x00 OUT (R/W), 0x04 IN (R, synchronised).
`default_nettype none

module periph_gpio #(
    parameter int OUT_W = 8,
    parameter int IN_W  = 8
) (
    input  wire              clk,
    input  wire              rst,
    input  wire              req,
    input  wire              we,
    input  wire  [5:0]       addr,
    input  wire  [31:0]      wdata,
    output logic [31:0]      rdata,
    output logic [OUT_W-1:0] gpio_out,
    input  wire  [IN_W-1:0]  gpio_in
);

    logic [IN_W-1:0] in_s1, in_s2;

    always_ff @(posedge clk) begin
        in_s1 <= gpio_in;
        in_s2 <= in_s1;
        if (rst)                             gpio_out <= '0;
        else if (req && we && addr == 6'd0) gpio_out <= wdata[OUT_W-1:0];
        if (req && !we) begin
            case (addr)
                6'd0:    rdata <= 32'(gpio_out);
                6'd1:    rdata <= 32'(in_s2);
                default: rdata <= '0;
            endcase
        end
    end

    wire unused = &{1'b0, wdata};

endmodule

`default_nettype wire
