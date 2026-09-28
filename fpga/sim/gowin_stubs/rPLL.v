// Lint/simulation stub of the Gowin rPLL primitive (ports and parameters only).
// Used by `make lint` for board tops; CLKOUT simply follows CLKIN.
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
module rPLL #(
    parameter FCLKIN = "100.0",
    parameter DYN_IDIV_SEL = "false",
    parameter IDIV_SEL = 0,
    parameter DYN_FBDIV_SEL = "false",
    parameter FBDIV_SEL = 0,
    parameter DYN_ODIV_SEL = "false",
    parameter ODIV_SEL = 8,
    parameter PSDA_SEL = "0000",
    parameter DYN_DA_EN = "false",
    parameter DUTYDA_SEL = "1000",
    parameter CLKOUT_FT_DIR = 1'b1,
    parameter CLKOUTP_FT_DIR = 1'b1,
    parameter CLKOUT_DLY_STEP = 0,
    parameter CLKOUTP_DLY_STEP = 0,
    parameter CLKFB_SEL = "internal",
    parameter CLKOUT_BYPASS = "false",
    parameter CLKOUTP_BYPASS = "false",
    parameter CLKOUTD_BYPASS = "false",
    parameter DYN_SDIV_SEL = 2,
    parameter CLKOUTD_SRC = "CLKOUT",
    parameter CLKOUTD3_SRC = "CLKOUT",
    parameter DEVICE = "GW1NR-9C"
) (
    output wire CLKOUT,
    output wire LOCK,
    output wire CLKOUTP,
    output wire CLKOUTD,
    output wire CLKOUTD3,
    input  wire RESET,
    input  wire RESET_P,
    input  wire CLKIN,
    input  wire CLKFB,
    input  wire [5:0] FBDSEL,
    input  wire [5:0] IDSEL,
    input  wire [5:0] ODSEL,
    input  wire [3:0] PSDA,
    input  wire [3:0] DUTYDA,
    input  wire [3:0] FDLY
);
    assign CLKOUT   = CLKIN;
    assign CLKOUTP  = CLKIN;
    assign CLKOUTD  = CLKIN;
    assign CLKOUTD3 = CLKIN;
    assign LOCK     = ~RESET;
endmodule
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNUSEDSIGNAL */
