// Signal bus, effect slots and the output mixer (trs.md 5.1). Once per sample (tick):
//   S0 synth, S1 IN1, S2 IN2, S3 LFO1, S4 LFO2, S5 SYNC (+-1), S6 ENV, S7 GATE (0/1) are latched;
//   slots run in order, slot k writes S[8 + k] (a slot reading a later slot sees its previous
//   sample); then OUT  = softclip(sat21(sum GAIN_i * S_i >> 16) + OUT_DC)
//                 OUT2 = softclip(sat21(S[SEL2] * GAIN2 >> 16) + OUT2_DC).
// Bit-exact model: fpga/model/synthmodel/avk.py (AvkBus).
//
// Adding an effect: a module with the slot interface (see slot_math.sv), a TYPE_ID, one line in
// the generate case below, and a descriptor in the firmware. SLOT_TYPES lists the slots.
//
// CPU registers (byte offsets in the 128 KB window at 0x3000_0000):
//   0x0_0000 OUT_DC  0x0_0004 OUT2_DC  0x0_0008 OUT2_SEL  0x0_000C OUT2_GAIN
//   0x0_0040 + 4i  GAIN[i] (Q2.16)     0x0_0100 + 4i  BUS[i] (R, current value)
//   0x1_0000 + 0x100 k: slot k: 0x00 TYPE_ID (R)  0x04 SEL_A  0x08 SEL_B  0x0C BYPASS
//                               0x10 MEM_BASE  0x14 MEM_SIZE  0x40 + 4j PARAM[j]
`default_nettype none

module fx_bus #(
    parameter int                     NUM_SLOTS  = 2,
    parameter logic [8*NUM_SLOTS-1:0] SLOT_TYPES = {NUM_SLOTS{8'd1}}  // slot k: [8k +: 8]
) (
    input  wire                clk,
    input  wire                rst,
    input  wire                tick,
    input  wire                req,
    input  wire                we,
    input  wire  [16:0]        addr,
    input  wire  [31:0]        wdata,
    output logic [31:0]        rdata,
    input  wire signed [17:0]  synth,
    input  wire signed [17:0]  in1,
    input  wire signed [17:0]  in2,
    input  wire signed [17:0]  lfo1,
    input  wire signed [17:0]  lfo2,
    input  wire                sync,
    input  wire signed [17:0]  env,
    input  wire                gate,
    output logic signed [17:0] out,
    output logic signed [17:0] out2
);

    localparam int NB = 8 + NUM_SLOTS;
    localparam int BW = $clog2(NB);
    localparam int KW = NUM_SLOTS > 1 ? $clog2(NUM_SLOTS) : 1;
    localparam logic signed [17:0] ONE = 18'sd65536;

    // ------------------------------------------------------------ registers
    logic signed [17:0] gain [NB];
    logic signed [17:0] out_dc, out2_dc, gain2;
    logic [BW-1:0]      sel2;
    logic [BW-1:0]      sel_a [NUM_SLOTS];
    logic [BW-1:0]      sel_b [NUM_SLOTS];
    logic               bypass [NUM_SLOTS];
    logic [31:0]        mem_base [NUM_SLOTS];
    logic [31:0]        mem_size [NUM_SLOTS];
    logic signed [17:0] s [NB];

    wire        is_slot = addr[16];
    wire [7:0]  sk      = addr[15:8];
    wire [5:0]  sreg    = addr[7:2];
    wire [13:0] mreg    = addr[15:2];
    logic [NUM_SLOTS-1:0] p_we;

    always_comb begin
        p_we = '0;
        if (req && we && is_slot && sreg >= 6'd16 && sk < 8'(NUM_SLOTS)) p_we[sk[KW-1:0]] = 1'b1;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < NB; i++) gain[i] <= i == 0 ? ONE : '0;
            out_dc  <= '0;
            out2_dc <= '0;
            gain2   <= ONE;
            sel2    <= BW'(3);  // LFO1
            for (int k = 0; k < NUM_SLOTS; k++) begin
                sel_a[k]    <= BW'(1);
                sel_b[k]    <= BW'(2);
                bypass[k]   <= 1'b0;
                mem_base[k] <= '0;
                mem_size[k] <= '0;
            end
        end else if (req && we) begin
            if (!is_slot) begin
                case (mreg)
                    14'd0: out_dc  <= wdata[17:0];
                    14'd1: out2_dc <= wdata[17:0];
                    14'd2: sel2    <= wdata[BW-1:0];
                    14'd3: gain2   <= wdata[17:0];
                    default: if (mreg >= 14'd16 && mreg < 14'(16 + NB)) gain[BW'(mreg - 14'd16)] <= wdata[17:0];
                endcase
            end else if (sk < 8'(NUM_SLOTS)) begin
                case (sreg)
                    6'd1: sel_a[sk[KW-1:0]]    <= wdata[BW-1:0];
                    6'd2: sel_b[sk[KW-1:0]]    <= wdata[BW-1:0];
                    6'd3: bypass[sk[KW-1:0]]   <= wdata[0];
                    6'd4: mem_base[sk[KW-1:0]] <= wdata;
                    6'd5: mem_size[sk[KW-1:0]] <= wdata;
                    default: ;
                endcase
            end
        end
    end

    always_ff @(posedge clk) begin
        if (req && !we) begin
            if (!is_slot) begin
                if (mreg >= 14'd64 && mreg < 14'(64 + NB)) rdata <= 32'(s[BW'(mreg - 14'd64)]);
                else if (mreg >= 14'd16 && mreg < 14'(16 + NB)) rdata <= 32'(gain[BW'(mreg - 14'd16)]);
                else case (mreg)
                    14'd0: rdata <= 32'(out_dc);
                    14'd1: rdata <= 32'(out2_dc);
                    14'd2: rdata <= 32'(sel2);
                    14'd3: rdata <= 32'(gain2);
                    default: rdata <= '0;
                endcase
            end else if (sk < 8'(NUM_SLOTS)) begin
                case (sreg)
                    6'd0: rdata <= {24'b0, SLOT_TYPES[8 * sk[KW-1:0] +: 8]};
                    6'd1: rdata <= 32'(sel_a[sk[KW-1:0]]);
                    6'd2: rdata <= 32'(sel_b[sk[KW-1:0]]);
                    6'd3: rdata <= 32'(bypass[sk[KW-1:0]]);
                    6'd4: rdata <= mem_base[sk[KW-1:0]];
                    6'd5: rdata <= mem_size[sk[KW-1:0]];
                    default: rdata <= '0;
                endcase
            end else begin
                rdata <= '0;
            end
        end
    end

    // ---------------------------------------------------------------- slots
    logic [NUM_SLOTS-1:0] start, done;
    logic signed [17:0]   sa, sb;
    logic signed [17:0]   y [NUM_SLOTS];

    for (genvar k = 0; k < NUM_SLOTS; k++) begin : g_slot
        case (SLOT_TYPES[8*k +: 8])
            8'd1: begin : g_math
                slot_math u_slot (
                    .clk(clk), .rst(rst), .start(start[k]), .a(sa), .b(sb),
                    .p_we(p_we[k]), .p_addr(4'(sreg - 6'd16)), .p_wdata(wdata), .y(y[k]), .done(done[k])
                );
            end
            default: begin : g_none  // unknown type: passes A through
                always_ff @(posedge clk) begin
                    y[k]    <= sa;
                    done[k] <= start[k];
                end
            end
        endcase
    end

    // ------------------------------------------------------------ sequencer
    typedef enum logic [2:0] {IDLE, SLOT_GO, SLOT_WAIT, MIX, CLIP} state_t;
    state_t        state;
    logic [KW-1:0] k;
    logic [BW-1:0] i;
    logic signed [45:0] acc;
    logic signed [20:0] mix, mix2;
    logic signed [17:0] clip1, clip2;
    logic [1:0]    wait_clip;

    function automatic logic signed [20:0] sat21(input logic signed [46:0] x);
        if (x > 47'sd1048575) return 21'sd1048575;
        if (x < -47'sd1048576) return -21'sd1048576;
        return x[20:0];
    endfunction

    wire signed [35:0] mprod  = gain[i] * s[i];
    wire signed [35:0] mprod2 = s[sel2] * gain2;

    always_ff @(posedge clk) begin
        start <= '0;
        if (rst) begin
            state <= IDLE;
            out   <= '0;
            out2  <= '0;
            mix   <= '0;
            mix2  <= '0;
            for (int n = 0; n < NB; n++) s[n] <= '0;
        end else begin
            case (state)
                IDLE: if (tick) begin
                    s[0] <= synth;
                    s[1] <= in1;
                    s[2] <= in2;
                    s[3] <= lfo1;
                    s[4] <= lfo2;
                    s[5] <= sync ? ONE : -ONE;
                    s[6] <= env;
                    s[7] <= gate ? ONE : '0;
                    k     <= '0;
                    state <= SLOT_GO;
                end
                SLOT_GO: begin
                    sa       <= s[sel_a[k]];
                    sb       <= s[sel_b[k]];
                    start[k] <= 1'b1;
                    state    <= SLOT_WAIT;
                end
                SLOT_WAIT: if (done[k]) begin
                    s[BW'(8 + 32'(k))] <= bypass[k] ? sa : y[k];
                    if (k == KW'(NUM_SLOTS - 1)) begin
                        state <= MIX;
                        i     <= '0;
                        acc   <= '0;
                    end else begin
                        k     <= k + 1'b1;
                        state <= SLOT_GO;
                    end
                end
                MIX: begin
                    acc <= acc + 46'(mprod);
                    i   <= i + 1'b1;
                    if (i == BW'(NB - 1)) begin
                        mix       <= sat21(47'(sat21(47'((acc + 46'(mprod)) >>> 16))) + 47'(out_dc));
                        mix2      <= sat21(47'(sat21(47'(mprod2) >>> 16)) + 47'(out2_dc));
                        wait_clip <= 2'd3;
                        state     <= CLIP;
                    end
                end
                CLIP: begin
                    if (wait_clip == 2'd0) begin
                        out   <= clip1;
                        out2  <= clip2;
                        state <= IDLE;
                    end
                    wait_clip <= wait_clip - 2'd1;
                end
                default: state <= IDLE;
            endcase
        end
    end

    softclip #(.IN_W(21)) u_clip1 (.clk(clk), .x(mix), .y(clip1));
    softclip #(.IN_W(21)) u_clip2 (.clk(clk), .x(mix2), .y(clip2));

    wire unused = &{1'b0, wdata[31:18], addr[1:0], mem_base[0], mem_size[0]};

endmodule

`default_nettype wire
