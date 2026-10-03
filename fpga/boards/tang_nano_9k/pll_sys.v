// sys_clk PLL for Tang Nano 9K (GW1NR-9C): 27 MHz -> 99 MHz.
// FCLKOUT = 27 * (FBDIV_SEL + 1) / (IDIV_SEL + 1) = 27 * 11 / 3 = 99 MHz,
// VCO = 99 * ODIV_SEL = 792 MHz, PFD = 9 MHz. fs = 99e6 / 2048 = 48339.84 Hz (+0.7 %).
// Vendor primitive: keep it in fpga/boards/ only.
module pll_sys (
    input  wire clkin,   // 27 MHz
    output wire clkout,  // 99 MHz
    output wire lock
);
    /* verilator lint_off PINCONNECTEMPTY */
    rPLL #(
        .FCLKIN          ("27"),
        .DYN_IDIV_SEL    ("false"),
        .IDIV_SEL        (2),
        .DYN_FBDIV_SEL   ("false"),
        .FBDIV_SEL       (10),
        .DYN_ODIV_SEL    ("false"),
        .ODIV_SEL        (8),
        .PSDA_SEL        ("0000"),
        .DYN_DA_EN       ("true"),
        .DUTYDA_SEL      ("1000"),
        .CLKOUT_FT_DIR   (1'b1),
        .CLKOUTP_FT_DIR  (1'b1),
        .CLKOUT_DLY_STEP (0),
        .CLKOUTP_DLY_STEP(0),
        .CLKFB_SEL       ("internal"),
        .CLKOUT_BYPASS   ("false"),
        .CLKOUTP_BYPASS  ("false"),
        .CLKOUTD_BYPASS  ("false"),
        .DYN_SDIV_SEL    (2),
        .CLKOUTD_SRC     ("CLKOUT"),
        .CLKOUTD3_SRC    ("CLKOUT"),
        .DEVICE          ("GW1NR-9C")
    ) u_rpll (
        .CLKOUT  (clkout),
        .LOCK    (lock),
        .CLKOUTP (),
        .CLKOUTD (),
        .CLKOUTD3(),
        .RESET   (1'b0),
        .RESET_P (1'b0),
        .CLKIN   (clkin),
        .CLKFB   (1'b0),
        .FBDSEL  (6'b0),
        .IDSEL   (6'b0),
        .ODSEL   (6'b0),
        .PSDA    (4'b0),
        .DUTYDA  (4'b0),
        .FDLY    (4'b0)
    );
    /* verilator lint_on PINCONNECTEMPTY */
endmodule
