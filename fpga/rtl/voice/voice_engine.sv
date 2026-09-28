// Polyphonic voice engine, time-multiplexed: NUM_VOICES voices per sample through one
// datapath with a shared 25x18 multiplier (schedule in the sequencer below).
// Per voice: 2 NCO (saw / square-PWM / triangle / sine) + noise -> mix -> Chamberlin SVF
// (2x oversampled, LP/BP/HP) -> VCA (ADSR1 x velocity x AM); ADSR2 -> cutoff. 22 clk per voice.
// Bit-exact model: fpga/model/synthmodel/voice.py (the arithmetic is specified there).
//
// CPU registers (byte offsets in the 128 KB window):
//   voice k (addr[16] = 0): base k * 0x40
//     0x00 PITCH1  0x04 PITCH2   log pitch, 21 bit
//     0x08 GATE    bit0 gate, bit1 retrigger toggle
//     0x0C VEL_AMP Q2.16   0x10 CUT_OFS signed pitch units
//     0x14 STATUS  R: {st2[23:22], st1[21:20], 2'b0, env1[17:0]}
//   global (addr[16] = 1):
//     0x00 WAVES {wave2[3:2], wave1[1:0]}  0x04 PW  0x08 G1  0x0C G2  0x10 GN
//     0x14 CUTOFF  0x18 ENV2_DEPTH  0x1C RES_Q  0x20 FMODE  0x24 MASTER
//     0x28 A1  0x2C D1  0x30 S1  0x34 R1  0x38 A2  0x3C D2  0x40 S2  0x44 R2
//          (A/D/R: {shift[21:17], mant[16:0]}; S: Q0.16)
//     0x48 PM  0x4C CM  0x50 AM     global pitch / cutoff offsets, amplitude Q2.16
//     0x54 INFO R: {NUM_VOICES[15:0]}
`default_nettype none

module voice_engine #(
    parameter int NUM_VOICES = 8
) (
    input  wire                clk,
    input  wire                rst,
    input  wire                tick,       // start of a sample
    // CPU
    input  wire                req,
    input  wire                we,
    input  wire  [16:0]        addr,
    input  wire  [31:0]        wdata,
    output logic [31:0]        rdata,
    // per-sample modulation from the modulation unit (added to PM/CM, multiplies AM)
    input  wire signed [22:0]  pm_ext,
    input  wire signed [22:0]  cm_ext,
    input  wire signed [17:0]  am_ext,     // Q2.16, 1.0 = no change
    // output
    output logic signed [19:0] s0,         // Q4.16
    output logic               s0_valid,
    output logic               busy
);

    localparam int VW = (NUM_VOICES > 1) ? $clog2(NUM_VOICES) : 1;

    localparam logic signed [32:0] ONE30      = 33'sd1073741824;
    localparam logic signed [32:0] ATK_TARGET = 33'sd1395864371;
    localparam logic signed [32:0] REL_TARGET = -33'sd1075839;
    localparam logic signed [24:0] PI_HALF    = 25'sd102944;
    localparam logic signed [24:0] THIRD      = 25'sd21845;
    localparam logic signed [22:0] C_MAX      = 23'sd1995158;
    localparam logic [20:0]        PITCH_MAX  = '1;
    localparam logic [31:0]        LFSR_TAPS  = 32'hD000_0001;

    localparam logic [1:0] IDLE = 2'd0, ATTACK = 2'd1, DECAY = 2'd2, RELEASE = 2'd3;

    // ------------------------------------------------------ global registers
    logic [1:0]         wave1, wave2, fmode;
    logic [15:0]        pw;
    logic signed [17:0] g1, g2, gn, res_q, master, am_reg;
    logic [20:0]        cutoff;
    logic signed [21:0] env2_depth;
    logic [21:0]        a1c, d1c, r1c, a2c, d2c, r2c;
    logic [16:0]        s1, s2;
    logic signed [22:0] pm_reg, cm_reg;

    wire        is_glob = addr[16];
    wire [5:0]  greg    = addr[7:2];
    wire [3:0]  vreg    = addr[5:2];
    wire [VW-1:0] vsel  = addr[VW+5:6];

    always_ff @(posedge clk) begin
        if (rst) begin
            wave1 <= 2'd0; wave2 <= 2'd0; fmode <= 2'd0; pw <= 16'h8000;
            g1 <= 18'sd65536; g2 <= '0; gn <= '0;
            cutoff <= C_MAX[20:0]; env2_depth <= '0; res_q <= 18'sd65536;
            master <= 18'sd65536; am_reg <= 18'sd65536;
            a1c <= '0; d1c <= '0; r1c <= '0; a2c <= '0; d2c <= '0; r2c <= '0;
            s1 <= 17'd65536; s2 <= '0;
            pm_reg <= '0; cm_reg <= '0;
        end else if (req && we && is_glob) begin
            case (greg)
                6'd0:  {wave2, wave1} <= wdata[3:0];
                6'd1:  pw <= wdata[15:0];
                6'd2:  g1 <= wdata[17:0];
                6'd3:  g2 <= wdata[17:0];
                6'd4:  gn <= wdata[17:0];
                6'd5:  cutoff <= wdata[20:0];
                6'd6:  env2_depth <= wdata[21:0];
                6'd7:  res_q <= wdata[17:0];
                6'd8:  fmode <= wdata[1:0];
                6'd9:  master <= wdata[17:0];
                6'd10: a1c <= wdata[21:0];
                6'd11: d1c <= wdata[21:0];
                6'd12: s1 <= wdata[16:0];
                6'd13: r1c <= wdata[21:0];
                6'd14: a2c <= wdata[21:0];
                6'd15: d2c <= wdata[21:0];
                6'd16: s2 <= wdata[16:0];
                6'd17: r2c <= wdata[21:0];
                6'd18: pm_reg <= wdata[22:0];
                6'd19: cm_reg <= wdata[22:0];
                6'd20: am_reg <= wdata[17:0];
                default: ;
            endcase
        end
    end

    // ------------------------------------------- per-voice registers (CPU writes)
    logic [20:0]        r_pitch1 [NUM_VOICES];
    logic [20:0]        r_pitch2 [NUM_VOICES];
    logic [1:0]         r_gate   [NUM_VOICES];  // {retrig toggle, gate}
    logic signed [17:0] r_vel    [NUM_VOICES];
    logic signed [21:0] r_cofs   [NUM_VOICES];

    wire vwr = req && we && !is_glob;

    always_ff @(posedge clk) begin
        if (vwr && vreg == 4'd0) r_pitch1[vsel] <= wdata[20:0];
        if (vwr && vreg == 4'd1) r_pitch2[vsel] <= wdata[20:0];
        if (vwr && vreg == 4'd2) r_gate[vsel]   <= wdata[1:0];
        if (vwr && vreg == 4'd3) r_vel[vsel]    <= wdata[17:0];
        if (vwr && vreg == 4'd4) r_cofs[vsel]   <= wdata[21:0];
    end

    // ------------------------------------------------ per-voice state (engine)
    typedef struct packed {
        logic [31:0] ph1, ph2;
        logic [30:0] e1, e2;
        logic [1:0]  st1, st2;
        logic        gprev, rtprev;
        logic signed [23:0] lp, bp;
    } vstate_t;

    vstate_t st_mem [NUM_VOICES];
    logic [23:0] status_mem [NUM_VOICES];

    // ------------------------------------------------------------ sequencer
    logic [VW-1:0]  v;
    logic [4:0]     t;
    logic           run;
    logic           fin;     // master multiply after the last voice
    logic [1:0]     fin_t;

    // voice data read at t = 0, valid from t = 1
    logic [20:0]        p1_r, p2_r;
    logic [1:0]         gate_r;
    logic signed [17:0] vel_r;
    logic signed [21:0] cofs_r;
    vstate_t            s;

    always_ff @(posedge clk) begin
        if (run && t == 5'd0) begin
            p1_r   <= r_pitch1[v];
            p2_r   <= r_pitch2[v];
            gate_r <= r_gate[v];
            vel_r  <= r_vel[v];
            cofs_r <= r_cofs[v];
            s      <= st_mem[v];
        end
    end

    // --------------------------------------------------------- shared units
    logic signed [24:0] ma;
    logic signed [17:0] mb;
    logic signed [42:0] prod;
    assign prod = ma * mb;

    logic [20:0] p2i_in;
    logic        p2i_v;
    logic [31:0] p2i_out;
    /* verilator lint_off PINCONNECTEMPTY */
    pitch2inc u_p2i (.clk(clk), .rst(rst), .pitch(p2i_in), .in_valid(p2i_v), .inc(p2i_out), .out_valid());
    /* verilator lint_on PINCONNECTEMPTY */

    logic [31:0] rom_ph;
    logic [16:0] rom_q;
    logic [1:0]  rom_quad_q;
    wire  [9:0]  rom_idx = rom_ph[29:20];
    sine_quarter_rom u_sine (.clk(clk), .addr(rom_ph[30] ? ~rom_idx : rom_idx), .data(rom_q));
    always_ff @(posedge clk) rom_quad_q <= rom_ph[31:30];

    // ------------------------------------------------------ helper functions
    function automatic logic [20:0] clamp21(input logic signed [23:0] x);
        if (x < 0) return '0;
        if (x > 24'sd2097151) return PITCH_MAX;
        return x[20:0];
    endfunction

    function automatic logic signed [17:0] sat18(input logic signed [42:0] x);
        if (x > 43'sd131071) return 18'sd131071;
        if (x < -43'sd131072) return -18'sd131072;
        return x[17:0];
    endfunction

    function automatic logic signed [23:0] sat24(input logic signed [42:0] x);
        if (x > 43'sd8388607) return 24'sd8388607;
        if (x < -43'sd8388608) return -24'sd8388608;
        return x[23:0];
    endfunction

    /* verilator lint_off UNUSEDSIGNAL */  // quad[0] is folded into the ROM address
    function automatic logic signed [17:0] wave(input logic [1:0] w, input logic [31:0] ph,
                                                 input logic [15:0] pwv, input logic [16:0] rq,
                                                 input logic [1:0] quad);
        logic signed [18:0] u;
        logic signed [17:0] sn;
        u  = $signed({2'b00, ph[31:15]});
        sn = quad[1] ? -$signed({1'b0, rq}) : $signed({1'b0, rq});
        case (w)
            2'd0:    return 18'(u - 19'sd65536);
            2'd1:    return ph < {pwv, 16'h0} ? 18'sd65536 : -18'sd65536;
            2'd2:    return u < 19'sd65536 ? 18'((u <<< 1) - 19'sd65536) : 18'(19'sd196608 - (u <<< 1));
            default: return sn >>> 1;
        endcase
    endfunction
    /* verilator lint_on UNUSEDSIGNAL */

    // envelope: stage after gate edges, and the segment's target / coefficient
    function automatic logic [1:0] env_edge(input logic [1:0] st, input logic gate, input logic gprev,
                                            input logic rt);
        if (gate && (!gprev || rt)) return ATTACK;
        if (!gate && gprev && st != IDLE) return RELEASE;
        return st;
    endfunction

    function automatic logic signed [32:0] env_target(input logic [1:0] st, input logic [16:0] sus);
        case (st)
            ATTACK:  return ATK_TARGET;
            DECAY:   return 33'($signed({1'b0, sus, 14'b0}));
            default: return REL_TARGET;
        endcase
    endfunction

    function automatic logic [21:0] env_coef(input logic [1:0] st, input logic [21:0] a, input logic [21:0] d,
                                             input logic [21:0] r);
        case (st)
            ATTACK:  return a;
            DECAY:   return d;
            default: return r;
        endcase
    endfunction

    // --------------------------------------------------------------- datapath
    logic [1:0]         st1a, st2a;           // stage after edge detection
    logic [4:0]         sh1, sh2;
    logic [30:0]        e1n, e2n;             // updated envelopes, 0..2^30
    logic [1:0]         st1n, st2n;
    logic [31:0]        ph1n, ph2n, incc;
    logic signed [17:0] o1, o2, nz, x, a, theta, f, q;
    logic signed [42:0] acc;
    logic signed [23:0] lp, bp, hp;
    logic signed [24:0] sum;
    logic [31:0]        lfsr;
    logic signed [17:0] am_eff;
    logic signed [22:0] pm_tot, cm_tot;

    wire rt = gate_r[1] != s.rtprev;
    wire [1:0]  st1e = env_edge(s.st1, gate_r[0], s.gprev, rt);
    wire [21:0] c1   = env_coef(st1e, a1c, d1c, r1c);
    wire [21:0] c2   = env_coef(st2a, a2c, d2c, r2c);
    wire signed [17:0] env1q = $signed({1'b0, e1n[30:14]});

    // env segment update from the product (used at t = 2 and t = 3)
    function automatic logic signed [33:0] env_add(input logic [30:0] e, input logic signed [42:0] p,
                                                   input logic [4:0] sh);
        return $signed({3'b0, e}) + 34'(p >>> sh);
    endfunction

    wire signed [33:0] e1_sum = env_add(s.e1, prod, sh1);
    wire signed [33:0] e2_sum = env_add(s.e2, prod, sh2);

    wire signed [17:0] q_c  = (res_q < 18'sd131072 - f - 18'sd4096) ? res_q : 18'sd131072 - f - 18'sd4096;
    wire signed [23:0] hp_c = sat24(43'(x) - 43'(lp) - (prod >>> 16));
    wire signed [23:0] bp_c = sat24(43'(bp) + (prod >>> 16));
    logic signed [17:0] y_c;
    always_comb begin
        case (fmode)
            2'd1:    y_c = sat18(43'(bp_c));
            2'd2:    y_c = sat18(43'(hp));
            default: y_c = sat18(43'(lp));
        endcase
    end

    // sine ROM address: osc1 phase at t = 5, osc2 at t = 6 (data one clk later)
    assign rom_ph = (t == 5'd5 ? s.ph1 : s.ph2) + p2i_out;

    wire signed [23:0] c_sum = $signed({3'b0, cutoff}) + 24'(cofs_r) + 24'(prod >>> 16) + 24'(cm_tot);
    wire signed [42:0] mix_sum = acc + prod;

    always_ff @(posedge clk) begin
        s0_valid <= 1'b0;
        p2i_v    <= 1'b0;
        if (rst) begin
            run    <= 1'b0;
            fin    <= 1'b0;
            fin_t  <= '0;
            t      <= '0;
            v      <= '0;
            lfsr   <= 32'd1;
            s0     <= '0;
            busy   <= 1'b0;
            am_eff <= 18'sd65536;
            pm_tot <= '0;
            cm_tot <= '0;
        end else if (tick && !run && !fin) begin
            run    <= 1'b1;
            busy   <= 1'b1;
            v      <= '0;
            t      <= '0;
            sum    <= '0;
            pm_tot <= pm_reg + pm_ext;
            cm_tot <= cm_reg + cm_ext;
            ma     <= 25'(am_reg);
            mb     <= am_ext;
            fin_t  <= 2'd1;  // am_eff from the product at t = 0 of voice 0
        end else if (run) begin
            if (fin_t == 2'd1) begin
                am_eff <= sat18(prod >>> 16);
                fin_t  <= 2'd0;
            end
            t <= t + 5'd1;
            case (t)
                5'd1: begin
                    st1a   <= st1e;
                    st2a   <= env_edge(s.st2, gate_r[0], s.gprev, rt);
                    ma     <= 25'(c1[16:0]);
                    mb     <= 18'((env_target(st1e, s1) - $signed({2'b0, s.e1})) >>> 14);
                    sh1    <= c1[21:17];
                    p2i_in <= clamp21($signed({3'b0, p1_r}) + 24'(pm_tot));
                    p2i_v  <= 1'b1;
                end
                5'd2: begin
                    // ADSR1 result
                    if (st1a == IDLE) begin
                        e1n <= '0; st1n <= IDLE;
                    end else if (st1a == ATTACK && e1_sum >= 34'(ONE30)) begin
                        e1n <= 31'(ONE30); st1n <= DECAY;
                    end else if (st1a == RELEASE && e1_sum <= 0) begin
                        e1n <= '0; st1n <= IDLE;
                    end else begin
                        e1n <= e1_sum[30:0]; st1n <= st1a;
                    end
                    ma     <= 25'(c2[16:0]);
                    mb     <= 18'((env_target(st2a, s2) - $signed({2'b0, s.e2})) >>> 14);
                    sh2    <= c2[21:17];
                    p2i_in <= clamp21($signed({3'b0, p2_r}) + 24'(pm_tot));
                    p2i_v  <= 1'b1;
                end
                5'd3: begin
                    // ADSR2 result, then env2 x depth
                    if (st2a == IDLE) begin
                        e2n <= '0; st2n <= IDLE;
                        ma  <= 25'(env2_depth);
                        mb  <= '0;
                    end else if (st2a == ATTACK && e2_sum >= 34'(ONE30)) begin
                        e2n <= 31'(ONE30); st2n <= DECAY;
                        ma  <= 25'(env2_depth);
                        mb  <= 18'sd65536;
                    end else if (st2a == RELEASE && e2_sum <= 0) begin
                        e2n <= '0; st2n <= IDLE;
                        ma  <= 25'(env2_depth);
                        mb  <= '0;
                    end else begin
                        e2n <= e2_sum[30:0]; st2n <= st2a;
                        ma  <= 25'(env2_depth);
                        mb  <= 18'(e2_sum >>> 14);
                    end
                end
                5'd4: begin
                    // cutoff (inc1 / inc2 / incc arrive at t = 5 / 6 / 8)
                    p2i_in <= c_sum < 0 ? '0 : c_sum > 24'(C_MAX) ? C_MAX[20:0] : c_sum[20:0];
                    p2i_v  <= 1'b1;
                    ma     <= 25'(env1q);
                    mb     <= vel_r;
                end
                5'd5: begin
                    ph1n <= s.ph1 + p2i_out;
                    ma   <= 25'(sat18(prod >>> 16));
                    mb   <= am_eff;
                end
                5'd6: begin
                    ph2n <= s.ph2 + p2i_out;
                    a    <= sat18(prod >>> 16);
                    o1   <= wave(wave1, ph1n, pw, rom_q, rom_quad_q);
                    lfsr <= (lfsr >> 1) ^ (lfsr[0] ? LFSR_TAPS : 32'h0);
                end
                5'd7: begin
                    o2 <= wave(wave2, ph2n, pw, rom_q, rom_quad_q);
                    nz <= 18'($signed({2'b00, lfsr[31:15]}) - 19'sd65536);
                    ma <= 25'(o1);
                    mb <= g1;
                end
                5'd8: begin
                    incc <= p2i_out;
                    acc  <= prod;
                    ma   <= 25'(o2);
                    mb   <= g2;
                end
                5'd9: begin
                    acc <= mix_sum;
                    ma  <= 25'(nz);
                    mb  <= gn;
                end
                5'd10: begin
                    x  <= sat18(mix_sum >>> 16);
                    ma <= PI_HALF;
                    mb <= $signed({1'b0, incc[31:15]});
                end
                5'd11: begin
                    theta <= 18'(prod >>> 16);
                    ma    <= 25'(18'(prod >>> 16));
                    mb    <= 18'(prod >>> 16);
                end
                5'd12: begin
                    ma <= 25'(18'(prod >>> 17));  // theta^2
                    mb <= theta;
                end
                5'd13: begin
                    ma <= THIRD;
                    mb <= 18'(prod >>> 17);       // theta^3
                end
                5'd14: begin
                    f  <= theta - 18'(prod >>> 16);
                    ma <= 25'(s.bp);
                    mb <= theta - 18'(prod >>> 16);
                    bp <= s.bp;
                    lp <= s.lp;
                end
                5'd15, 5'd18: begin  // lp += f * bp; next q * bp
                    lp <= sat24(43'(lp) + (prod >>> 16));
                    q  <= q_c;
                    ma <= 25'(bp);
                    mb <= q_c;
                end
                5'd16, 5'd19: begin  // hp = x - lp - q * bp; next f * hp
                    hp <= hp_c;
                    ma <= 25'(hp_c);
                    mb <= f;
                end
                5'd17: begin         // bp += f * hp; next f * bp (second pass)
                    bp <= bp_c;
                    ma <= 25'(bp_c);
                    mb <= f;
                end
                5'd20: begin
                    bp <= bp_c;
                    ma <= 25'(y_c);
                    mb <= a;
                end
                5'd21: begin
                    sum <= sum + 25'(sat18(prod >>> 16));
                    st_mem[v] <= '{ph1: ph1n, ph2: ph2n, e1: e1n, e2: e2n, st1: st1n, st2: st2n,
                                   gprev: gate_r[0], rtprev: gate_r[1], lp: lp, bp: bp};
                    status_mem[v] <= {st2n, st1n, 2'b00, env1q};
                    t <= '0;
                    if (v == VW'(NUM_VOICES - 1)) begin
                        run <= 1'b0;
                        fin <= 1'b1;
                    end else begin
                        v <= v + 1'b1;
                    end
                end
                default: ;
            endcase
        end else if (fin) begin
            if (fin_t == 2'd0) begin
                ma    <= sum;
                mb    <= master;
                fin_t <= 2'd2;
            end else begin
                s0       <= (prod >>> 16) > 43'sd524287 ? 20'sd524287 :
                            (prod >>> 16) < -43'sd524288 ? -20'sd524288 : 20'(prod >>> 16);
                s0_valid <= 1'b1;
                fin      <= 1'b0;
                fin_t    <= 2'd0;
                busy     <= 1'b0;
            end
        end
    end

    // ------------------------------------------------------------- CPU read
    always_ff @(posedge clk) begin
        if (req && !we) begin
            if (!is_glob)
                rdata <= vreg == 4'd5 ? {8'b0, status_mem[vsel]} : '0;
            else case (greg)
                6'd0:  rdata <= {28'b0, wave2, wave1};
                6'd1:  rdata <= {16'b0, pw};
                6'd5:  rdata <= {11'b0, cutoff};
                6'd7:  rdata <= 32'(res_q);
                6'd9:  rdata <= 32'(master);
                6'd21: rdata <= 32'(NUM_VOICES);
                default: rdata <= '0;
            endcase
        end
    end

    wire unused = &{1'b0, q, rom_ph[19:0], incc[14:0], wdata[31:23], addr[15:VW+6], addr[1:0]};

endmodule

`default_nettype wire
