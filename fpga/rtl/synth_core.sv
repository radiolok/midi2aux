// Synth core (from stage 2): PicoRV32 SoC + audio path.
//
// Memory map (trs.md 8.2):
//   0x0000_0000  RAM, RAM_BYTES (code + data)
//   0x0010_0000  boot ROM (reset vector by default)
//   0x1000_0000  peripherals, 0x100 per block:
//                0 UART  1 TIMER  2 GPIO  3 MIDI  4 SYSINFO  5 SPI flash
//   0x3000_0000  audio output: 0x00 OUT (L), 0x04 OUT2 (R), Q2.16 (1.0 = МЕ)
// Unmapped accesses complete with zero data.
`default_nettype none

module synth_core #(
    parameter int          SYS_CLK_HZ      = 99_000_000,
    parameter int          FS_HZ           = 48_000,
    parameter int          DATA_W          = 18,
    parameter int          RAM_BYTES       = 32768,
    parameter logic [31:0] RESET_ADDR      = 32'h0010_0000,
    parameter string       RAM_INIT        = "",  // simulation only
    parameter int          UART_BAUD       = 115_200,
    parameter int          BOOT_WAIT_MS    = 500,
    parameter logic [31:0] FW_FLASH_OFFSET = 32'h0050_0000,
    parameter int          MIDI_BAUD       = 31_250
) (
    input  wire        clk,
    input  wire        rst,
    // MIDI and debug UART
    input  wire        midi_rx,
    input  wire        uart_rx,
    output logic       uart_tx,
    // SPI flash (firmware image)
    output logic       flash_sck,
    output logic       flash_mosi,
    input  wire        flash_miso,
    output logic       flash_cs_n,
    // DAC
    output logic       i2s_bck,
    output logic       i2s_lrck,
    output logic       i2s_din,
    output logic       dac_xsmt,
    // board
    output logic [5:0] led,
    input  wire  [1:0] btn,
    output logic       trap
);

    localparam int BCK_HALF = (SYS_CLK_HZ + 64 * FS_HZ) / (128 * FS_HZ);
    localparam int RAM_AW   = $clog2(RAM_BYTES / 4);
    localparam logic [31:0] VERSION = 32'h0002_0000;  // stage 2

    // ------------------------------------------------------------------ CPU
    logic        mem_valid, mem_instr, mem_ready;
    logic [31:0] mem_addr, mem_wdata, mem_rdata;
    logic [3:0]  mem_wstrb;

    /* verilator lint_off PINCONNECTEMPTY */
    picorv32 #(
        .ENABLE_COUNTERS     (1),
        .ENABLE_COUNTERS64   (0),
        .ENABLE_REGS_16_31   (1),
        .ENABLE_REGS_DUALPORT(1),
        .BARREL_SHIFTER      (1),
        .COMPRESSED_ISA      (1),
        .ENABLE_MUL          (1),
        .ENABLE_DIV          (1),
        .ENABLE_IRQ          (0),
        .CATCH_MISALIGN      (1),
        .CATCH_ILLINSN       (1),
        .PROGADDR_RESET      (RESET_ADDR),
        .STACKADDR           (32'(RAM_BYTES))
    ) u_cpu (
        .clk(clk), .resetn(!rst), .trap(trap),
        .mem_valid(mem_valid), .mem_instr(mem_instr), .mem_ready(mem_ready),
        .mem_addr(mem_addr), .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb), .mem_rdata(mem_rdata),
        .mem_la_read(), .mem_la_write(), .mem_la_addr(), .mem_la_wdata(), .mem_la_wstrb(),
        .pcpi_valid(), .pcpi_insn(), .pcpi_rs1(), .pcpi_rs2(),
        .pcpi_wr(1'b0), .pcpi_rd(32'b0), .pcpi_wait(1'b0), .pcpi_ready(1'b0),
        .irq(32'b0), .eoi(),
        .trace_valid(), .trace_data()
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // ------------------------------------------------------------ bus decode
    typedef enum logic [2:0] {SEL_NONE, SEL_RAM, SEL_ROM, SEL_PERIPH, SEL_AUDIO} sel_t;

    logic        req, we;
    sel_t        sel, sel_q;
    logic [3:0]  blk, blk_q;
    logic [5:0]  reg_addr;

    assign req      = mem_valid && !mem_ready;
    assign we       = |mem_wstrb;
    assign blk      = mem_addr[11:8];
    assign reg_addr = mem_addr[7:2];

    always_comb begin
        sel = SEL_NONE;
        if (mem_addr < 32'(RAM_BYTES))                sel = SEL_RAM;
        else if (mem_addr[31:12] == 20'h00100)        sel = SEL_ROM;  // 4 KB window
        else if (mem_addr[31:12] == 20'h10000)        sel = SEL_PERIPH;
        else if (mem_addr[31:12] == 20'h30000)        sel = SEL_AUDIO;
    end

    always_ff @(posedge clk) begin
        if (rst) mem_ready <= 1'b0;
        else     mem_ready <= req;
        sel_q <= sel;
        blk_q <= blk;
    end

    logic [31:0] ram_q, rom_q, audio_q;
    logic [31:0] prd [16];

    always_comb begin
        case (sel_q)
            SEL_RAM:    mem_rdata = ram_q;
            SEL_ROM:    mem_rdata = rom_q;
            SEL_PERIPH: mem_rdata = prd[blk_q];
            SEL_AUDIO:  mem_rdata = audio_q;
            default:    mem_rdata = '0;
        endcase
    end

    soc_ram #(.BYTES(RAM_BYTES), .INIT(RAM_INIT)) u_ram (
        .clk(clk), .en(req && sel == SEL_RAM), .we(mem_wstrb),
        .addr(mem_addr[RAM_AW+1:2]), .wdata(mem_wdata), .rdata(ram_q)
    );

    boot_rom u_rom (.clk(clk), .addr(mem_addr[11:2]), .data(rom_q));

    // ----------------------------------------------------------- peripherals
    logic [15:0] preq;

    always_comb begin
        preq = '0;
        if (req && sel == SEL_PERIPH) preq[blk] = 1'b1;
    end

    logic audio_tick, midi_act;
    logic [7:0] gpio_out;

    periph_uart #(.SYS_CLK_HZ(SYS_CLK_HZ), .BAUD(UART_BAUD)) u_uart (
        .clk(clk), .rst(rst), .req(preq[0]), .we(we), .addr(reg_addr), .wdata(mem_wdata),
        .rdata(prd[0]), .rx(uart_rx), .tx(uart_tx)
    );

    periph_timer u_timer (
        .clk(clk), .rst(rst), .req(preq[1]), .we(we), .addr(reg_addr), .rdata(prd[1]),
        .audio_tick(audio_tick)
    );

    periph_gpio #(.OUT_W(8), .IN_W(2)) u_gpio (
        .clk(clk), .rst(rst), .req(preq[2]), .we(we), .addr(reg_addr), .wdata(mem_wdata),
        .rdata(prd[2]), .gpio_out(gpio_out), .gpio_in(btn)
    );

    periph_midi #(.SYS_CLK_HZ(SYS_CLK_HZ), .BAUD(MIDI_BAUD)) u_midi (
        .clk(clk), .rst(rst), .req(preq[3]), .we(we), .addr(reg_addr), .wdata(mem_wdata),
        .rdata(prd[3]), .midi_rx(midi_rx), .activity(midi_act)
    );

    // SYSINFO
    always_ff @(posedge clk) begin
        if (preq[4]) begin
            case (reg_addr)
                6'd0:    prd[4] <= 32'h364B_5641;  // "AVK6"
                6'd1:    prd[4] <= VERSION;
                6'd2:    prd[4] <= 32'(SYS_CLK_HZ);
                6'd3:    prd[4] <= 32'(BCK_HALF);
                6'd4:    prd[4] <= 32'(RAM_BYTES);
                6'd5:    prd[4] <= 32'd0;          // NUM_VOICES (stage 3)
                6'd6:    prd[4] <= 32'(BOOT_WAIT_MS);
                6'd7:    prd[4] <= FW_FLASH_OFFSET;
                6'd8:    prd[4] <= 32'(UART_BAUD);
                default: prd[4] <= '0;
            endcase
        end
    end

    spi_master #(.NCS(1), .DIV_RST(1)) u_flash (
        .clk(clk), .rst(rst), .req(preq[5]), .we(we), .addr(reg_addr), .wdata(mem_wdata),
        .rdata(prd[5]), .sck(flash_sck), .mosi(flash_mosi), .miso(flash_miso), .cs_n(flash_cs_n)
    );

    for (genvar i = 6; i < 16; i++) begin : g_no_periph
        assign prd[i] = '0;
    end

    // LEDs: 0..3 from GPIO, 4 MIDI activity (stretched), 5 trap
    logic [22:0] act_cnt;
    always_ff @(posedge clk) begin
        if (rst)           act_cnt <= '0;
        else if (midi_act) act_cnt <= '1;
        else if (act_cnt != '0) act_cnt <= act_cnt - 23'd1;
    end
    assign led = {trap, act_cnt != '0, gpio_out[3:0]};

    // ----------------------------------------------------------------- audio
    logic                     bck_fall_stb;
    logic [5:0]               slot_next;
    logic signed [DATA_W-1:0] out_l, out_r, dac_l, dac_r;

    audio_clkgen #(.SYS_CLK_HZ(SYS_CLK_HZ), .FS_HZ(FS_HZ), .BCK_HALF(BCK_HALF)) u_clkgen (
        .clk(clk), .rst(rst), .bck(i2s_bck), .bck_fall_stb(bck_fall_stb),
        .slot_next(slot_next), .audio_tick(audio_tick)
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            out_l <= '0;
            out_r <= '0;
        end else if (req && sel == SEL_AUDIO && we) begin
            if (reg_addr == 6'd0) out_l <= mem_wdata[DATA_W-1:0];
            if (reg_addr == 6'd1) out_r <= mem_wdata[DATA_W-1:0];
        end
        if (req && sel == SEL_AUDIO && !we)
            audio_q <= reg_addr == 6'd0 ? 32'(out_l) : reg_addr == 6'd1 ? 32'(out_r) : '0;
    end

    dac_scale #(.DATA_W(DATA_W)) u_dac_l (.clk(clk), .x(out_l), .y(dac_l));
    dac_scale #(.DATA_W(DATA_W)) u_dac_r (.clk(clk), .x(out_r), .y(dac_r));

    i2s_tx #(.DATA_W(DATA_W)) u_i2s (
        .clk(clk), .rst(rst), .bck_fall_stb(bck_fall_stb), .slot_next(slot_next),
        .left(dac_l), .right(dac_r), .lrck(i2s_lrck), .din(i2s_din)
    );

    always_ff @(posedge clk) begin
        if (rst) dac_xsmt <= 1'b0;
        else     dac_xsmt <= 1'b1;
    end

    wire unused = &{1'b0, mem_instr, gpio_out[7:4], preq[15:6]};

endmodule

`default_nettype wire
