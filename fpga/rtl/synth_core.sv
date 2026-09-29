// Synth core (from stage 2): PicoRV32 SoC + audio path.
//
// Memory map (trs.md 8.2):
//   0x0000_0000  RAM, RAM_BYTES (code + data)
//   0x0010_0000  boot ROM (reset vector by default)
//   0x1000_0000  peripherals, 0x100 per block:
//                0 UART  1 TIMER  2 GPIO  3 MIDI  4 SYSINFO  5 SPI flash
//                6 POTS (MCP3208)  7 ENC (encoders)  8 LCD (ST7789)  9 SYNC  10 ADC (IN1/IN2)
//   0x2000_0000  voice engine (voice/voice_engine.sv): voices, then globals at +0x1_0000
//   0x2002_0000  modulation unit (voice/mod_unit.sv): LFOs, modulation matrix
//   0x3000_0000  signal bus, output mixer, slots (avk/fx_bus.sv): OUT (L), OUT2 (R)
//   0x4000_0000  external memory window (32-bit words, shared with the slots; wait states)
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
    parameter int          MIDI_BAUD       = 31_250,
    parameter int          NUM_VOICES      = 16,
    parameter int          SIM_FAST        = 0,     // SYSINFO flag: firmware shortens delays
    parameter int          NUM_SLOTS       = 2,
    parameter logic [8*NUM_SLOTS-1:0] SLOT_TYPES = {NUM_SLOTS{8'd1}},  // slot k: [8k +: 8]
    parameter int          MEM_WORDS       = 0      // external memory (xm_*) size, SYSINFO
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
    // panel: MCP3208 (potentiometers), encoders, ST7789 display
    output logic       pot_sck,
    output logic       pot_mosi,
    input  wire        pot_miso,
    output logic       pot_cs_n,
    input  wire  [3:0] enc_a,
    input  wire  [3:0] enc_b,
    input  wire  [3:0] enc_sw,
    output logic       lcd_sck,
    output logic       lcd_mosi,
    output logic       lcd_cs_n,
    output logic       lcd_dc,
    output logic       lcd_rst_n,
    output logic       lcd_bl,
    // AVK inputs: 2x AD7091R, SYNC comparator
    output logic       adc_convst_n,
    output logic       adc_cs_n,
    output logic       adc_sclk,
    input  wire        adc_sdo1,
    input  wire        adc_sdo2,
    input  wire        sync_in,
    // external memory (mem/mem_bram.sv or mem/sdram_ctrl.sv), protocol: mem/mem_arb.sv
    output logic        xm_req,
    output logic        xm_we,
    output logic [23:0] xm_addr,
    output logic [31:0] xm_wdata,
    output logic [3:0]  xm_be,
    input  wire         xm_ack,
    input  wire  [31:0] xm_rdata,
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
    localparam logic [31:0] VERSION = 32'h0007_0000;  // stage 7

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
    typedef enum logic [2:0] {SEL_NONE, SEL_RAM, SEL_ROM, SEL_PERIPH, SEL_VOICE, SEL_MOD, SEL_AUDIO, SEL_XMEM} sel_t;

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
        else if (mem_addr[31:17] == 15'h1000)         sel = SEL_VOICE;
        else if (mem_addr[31:12] == 20'h20020)        sel = SEL_MOD;
        else if (mem_addr[31:17] == 15'h1800)         sel = SEL_AUDIO;
        else if (mem_addr[31:26] == 6'b010000)        sel = SEL_XMEM;  // 64 MB window
    end

    logic cpu_xm_ack;

    always_ff @(posedge clk) begin
        if (rst) mem_ready <= 1'b0;
        else     mem_ready <= sel == SEL_XMEM ? cpu_xm_ack : req;
        sel_q <= sel;
        blk_q <= blk;
    end

    logic [31:0] ram_q, rom_q, audio_q, voice_q, mod_q, xm_q;
    logic [31:0] prd [16];

    always_comb begin
        case (sel_q)
            SEL_RAM:    mem_rdata = ram_q;
            SEL_ROM:    mem_rdata = rom_q;
            SEL_PERIPH: mem_rdata = prd[blk_q];
            SEL_VOICE:  mem_rdata = voice_q;
            SEL_MOD:    mem_rdata = mod_q;
            SEL_AUDIO:  mem_rdata = audio_q;
            SEL_XMEM:   mem_rdata = xm_q;
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
                6'd5:    prd[4] <= 32'(NUM_VOICES);
                6'd6:    prd[4] <= 32'(BOOT_WAIT_MS);
                6'd7:    prd[4] <= FW_FLASH_OFFSET;
                6'd8:    prd[4] <= 32'(UART_BAUD);
                6'd9:    prd[4] <= {31'b0, SIM_FAST != 0};
                6'd10:   prd[4] <= 32'(MEM_WORDS);
                6'd11:   prd[4] <= 32'(NUM_SLOTS);
                default: prd[4] <= '0;
            endcase
        end
    end

    spi_master #(.NCS(1), .DIV_RST(1)) u_flash (
        .clk(clk), .rst(rst), .req(preq[5]), .we(we), .addr(reg_addr), .wdata(mem_wdata),
        .rdata(prd[5]), .sck(flash_sck), .mosi(flash_mosi), .miso(flash_miso), .cs_n(flash_cs_n)
    );

    periph_pots #(.SYS_CLK_HZ(SYS_CLK_HZ)) u_pots (
        .clk(clk), .rst(rst), .req(preq[6]), .we(we), .addr(reg_addr), .rdata(prd[6]),
        .sck(pot_sck), .mosi(pot_mosi), .miso(pot_miso), .cs_n(pot_cs_n)
    );

    periph_enc #(.SYS_CLK_HZ(SYS_CLK_HZ), .N(4)) u_enc (
        .clk(clk), .rst(rst), .req(preq[7]), .we(we), .addr(reg_addr), .wdata(mem_wdata), .rdata(prd[7]),
        .enc_a(enc_a), .enc_b(enc_b), .enc_sw(enc_sw)
    );

    lcd_ctrl u_lcd (
        .clk(clk), .rst(rst), .req(preq[8]), .we(we), .addr(reg_addr), .wdata(mem_wdata), .rdata(prd[8]),
        .sck(lcd_sck), .mosi(lcd_mosi), .cs_n(lcd_cs_n), .dc(lcd_dc), .rst_n(lcd_rst_n), .bl(lcd_bl)
    );

    logic               sync_level, sync_edge;
    logic signed [17:0] in1, in2;

    sync_in u_sync (
        .clk(clk), .rst(rst), .tick(audio_tick), .req(preq[9]), .we(we), .addr(reg_addr), .wdata(mem_wdata),
        .rdata(prd[9]), .sync_pin(sync_in), .level(sync_level), .edge_tick(sync_edge)
    );

    adc_in #(.PERIOD(128 * BCK_HALF), .CONV_CYC((SYS_CLK_HZ / 1_000_000) * 7 / 10 + 1)) u_adc (
        .clk(clk), .rst(rst), .tick(audio_tick), .req(preq[10]), .we(we), .addr(reg_addr), .wdata(mem_wdata),
        .rdata(prd[10]), .convst_n(adc_convst_n), .cs_n(adc_cs_n), .sclk(adc_sclk),
        .sdo1(adc_sdo1), .sdo2(adc_sdo2), .in1(in1), .in2(in2)
    );

    for (genvar i = 11; i < 16; i++) begin : g_no_periph
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
    logic signed [19:0]       s0;
    logic                     s0_valid, engine_busy;

    audio_clkgen #(.SYS_CLK_HZ(SYS_CLK_HZ), .FS_HZ(FS_HZ), .BCK_HALF(BCK_HALF)) u_clkgen (
        .clk(clk), .rst(rst), .bck(i2s_bck), .bck_fall_stb(bck_fall_stb),
        .slot_next(slot_next), .audio_tick(audio_tick)
    );

    logic signed [22:0] mod_pm, mod_cm;
    logic signed [17:0] mod_am, lfo1, lfo2, env_out;
    logic signed [16:0] mod_pw;
    logic               gate_any;

    mod_unit u_mod (
        .clk(clk), .rst(rst), .tick(audio_tick),
        .req(req && sel == SEL_MOD), .we(we), .addr(mem_addr[7:0]), .wdata(mem_wdata), .rdata(mod_q),
        .in1(in1), .in2(in2), .sync(sync_level), .sync_edge(sync_edge), .env(env_out),
        .pm(mod_pm), .cm(mod_cm), .am(mod_am), .pw(mod_pw), .lfo1(lfo1), .lfo2(lfo2), .gate_out(gate_any)
    );

    voice_engine #(.NUM_VOICES(NUM_VOICES)) u_voices (
        .clk(clk), .rst(rst), .tick(audio_tick),
        .req(req && sel == SEL_VOICE), .we(we), .addr(mem_addr[16:0]), .wdata(mem_wdata), .rdata(voice_q),
        .pm_ext(mod_pm), .cm_ext(mod_cm), .am_ext(mod_am), .pw_ext(mod_pw), .sync_edge(sync_edge),
        .s0(s0), .s0_valid(s0_valid), .busy(engine_busy), .env_out(env_out)
    );

    wire signed [17:0] synth = s0 > 20'sd131071 ? 18'sd131071 : s0 < -20'sd131072 ? -18'sd131072 : s0[17:0];

    logic        sl_req, sl_we, sl_ack;
    logic [23:0] sl_addr;
    logic [31:0] sl_wdata, xm_rd;

    fx_bus #(.NUM_SLOTS(NUM_SLOTS), .SLOT_TYPES(SLOT_TYPES)) u_bus (
        .clk(clk), .rst(rst), .tick(audio_tick),
        .req(req && sel == SEL_AUDIO), .we(we), .addr(mem_addr[16:0]), .wdata(mem_wdata), .rdata(audio_q),
        .synth(synth), .in1(in1), .in2(in2), .lfo1(lfo1), .lfo2(lfo2), .sync(sync_level), .env(env_out),
        .gate(gate_any), .out(out_l), .out2(out_r),
        .m_req(sl_req), .m_we(sl_we), .m_addr(sl_addr), .m_wdata(sl_wdata), .m_ack(sl_ack), .m_rdata(xm_rd)
    );

    // external memory: slots first, then the CPU window (held while mem_valid, until the ack)
    mem_arb u_arb (
        .clk(clk), .rst(rst),
        .a_req(sl_req), .a_we(sl_we), .a_addr(sl_addr), .a_wdata(sl_wdata), .a_be(4'hF), .a_ack(sl_ack),
        .b_req(mem_valid && !mem_ready && sel == SEL_XMEM), .b_we(we), .b_addr(mem_addr[25:2]),
        .b_wdata(mem_wdata), .b_be(mem_wstrb), .b_ack(cpu_xm_ack),
        .rdata(xm_rd), .m_req(xm_req), .m_we(xm_we), .m_addr(xm_addr), .m_wdata(xm_wdata), .m_be(xm_be),
        .m_ack(xm_ack), .m_rdata(xm_rdata)
    );

    always_ff @(posedge clk) if (cpu_xm_ack) xm_q <= xm_rd;

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

    wire unused = &{1'b0, mem_instr, gpio_out[7:4], preq[15:11], s0_valid, engine_busy};

endmodule

`default_nettype wire
