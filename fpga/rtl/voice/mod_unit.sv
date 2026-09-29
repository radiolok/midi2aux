// Modulation unit: 2 global LFOs + 8-route modulation matrix -> pitch / cutoff / amplitude /
// pulse-width modulation of all voices. Bit-exact model: fpga/model/synthmodel/modunit.py.
// Registers (byte offsets):
//   0x00 LFO1_INC  0x04 LFO1_CFG {sync_reset[4], wave[2:0]}  0x08 LFO2_INC  0x0C LFO2_CFG
//   0x10 MODWHEEL Q2.16   0x14 AM_BASE Q2.16 (1.0: AM adds, 0: ring modulation)
//   0x18 AUX Q2.16 (CPU source)   0x1C GATE bit0
//   0x40 + 8k ROUTE_k {dst[10:8], via[7:4], src[3:0]}   0x44 + 8k DEPTH_k signed 24 bit
//   0x20 FOLLOW_SRC (0 IN1, 1 IN2)  0x24 FOLLOW_ATK  0x28 FOLLOW_REL (Q0.16): envelope follower,
//        source 10
//   R: 0x80 LFO1 value  0x84 LFO2 value  0x88 FOLLOW value
`default_nettype none

module mod_unit (
    input  wire                clk,
    input  wire                rst,
    input  wire                tick,
    input  wire                req,
    input  wire                we,
    input  wire  [7:0]         addr,
    input  wire  [31:0]        wdata,
    output logic [31:0]        rdata,
    // sources from the rest of the core
    input  wire signed [17:0]  in1,
    input  wire signed [17:0]  in2,
    input  wire                sync,
    input  wire                sync_edge,  // with tick: resets LFOs with SYNC_RESET
    input  wire signed [17:0]  env,
    // outputs, valid until the next computation (the engine latches them at tick)
    output logic signed [22:0] pm,
    output logic signed [22:0] cm,
    output logic signed [17:0] am,
    output logic signed [16:0] pw,
    output logic signed [17:0] lfo1,
    output logic signed [17:0] lfo2,
    output logic               gate_out   // GATE register (any key held), for the signal bus
);

    localparam logic signed [17:0] ONE = 18'sd65536;

    // ------------------------------------------------------------ registers
    logic [31:0]        inc [2];
    logic [2:0]         wave [2];
    logic [1:0]         sreset;
    logic signed [17:0] modwheel, am_base, aux;
    logic               gate, fsrc;
    logic [15:0]        fatk, frel;
    logic [3:0]         r_src [8];
    logic [3:0]         r_via [8];
    logic [2:0]         r_dst [8];
    logic signed [23:0] r_depth [8];

    always_ff @(posedge clk) begin
        if (rst) begin
            inc[0] <= '0; inc[1] <= '0; wave[0] <= '0; wave[1] <= '0; sreset <= '0;
            modwheel <= '0; am_base <= ONE; aux <= '0; gate <= 1'b0; fsrc <= 1'b0; fatk <= '0; frel <= '0;
            for (int k = 0; k < 8; k++) begin
                r_src[k] <= '0; r_via[k] <= '0; r_dst[k] <= '0; r_depth[k] <= '0;
            end
        end else if (req && we) begin
            if (addr[7:6] == 2'b01) begin
                if (addr[2]) r_depth[addr[5:3]] <= wdata[23:0];
                else begin
                    r_src[addr[5:3]] <= wdata[3:0];
                    r_via[addr[5:3]] <= wdata[7:4];
                    r_dst[addr[5:3]] <= wdata[10:8];
                end
            end else case (addr[7:2])
                6'd0: inc[0] <= wdata;
                6'd1: {sreset[0], wave[0]} <= {wdata[4], wdata[2:0]};
                6'd2: inc[1] <= wdata;
                6'd3: {sreset[1], wave[1]} <= {wdata[4], wdata[2:0]};
                6'd4: modwheel <= wdata[17:0];
                6'd5: am_base <= wdata[17:0];
                6'd6: aux <= wdata[17:0];
                6'd7: gate <= wdata[0];
                6'd8: fsrc <= wdata[0];
                6'd9: fatk <= wdata[15:0];
                6'd10: frel <= wdata[15:0];
                default: ;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (req && !we) begin
            case (addr[7:2])
                6'd32:   rdata <= 32'(lfo1);
                6'd33:   rdata <= 32'(lfo2);
                6'd34:   rdata <= 32'(follow);
                default: rdata <= '0;
            endcase
        end
    end

    // ------------------------------------------------------------------ LFOs
    function automatic logic [31:0] xorshift32(input logic [31:0] x);
        logic [31:0] y;
        y = x ^ (x << 13);
        y = y ^ (y >> 17);
        return y ^ (y << 5);
    endfunction

    function automatic logic signed [17:0] lfo_wave(input logic [31:0] ph, input logic [2:0] w,
                                                    input logic signed [17:0] rnd);
        logic signed [18:0] u, vq, t, ta;
        logic signed [37:0] tt;
        logic [16:0]        phq;
        u   = $signed({2'b00, ph[31:15]});
        phq = ph[31:15] + 17'h8000;  // + quarter period
        vq  = $signed({2'b00, phq});
        t   = vq < 19'sd65536 ? (vq <<< 1) - 19'sd65536 : 19'sd196608 - (vq <<< 1);
        ta  = t < 0 ? -t : t;
        tt  = t * ta;
        case (w)
            3'd0:    return 18'((t <<< 1) - 19'(tt >>> 16));
            3'd1:    return 18'(t);
            3'd2:    return 18'(u - 19'sd65536);
            3'd3:    return ph < 32'h8000_0000 ? ONE : -ONE;
            3'd4:    return rnd;
            3'd5:    return 18'(19'sd65535 - u);
            default: return '0;
        endcase
    endfunction

    logic [31:0]        ph [2];
    logic signed [17:0] rnd [2];
    logic [31:0]        rng;

    // phase update with wrap detection; LFO1 draws the random value first
    logic [32:0] nxt0, nxt1;
    logic [31:0] rng1, rng2;
    assign nxt0 = {1'b0, ph[0]} + {1'b0, inc[0]};
    assign nxt1 = {1'b0, ph[1]} + {1'b0, inc[1]};
    assign rng1 = (!(sync_edge && sreset[0]) && nxt0[32]) ? xorshift32(rng) : rng;
    assign rng2 = (!(sync_edge && sreset[1]) && nxt1[32]) ? xorshift32(rng1) : rng1;

    // ---------------------------------------------------------------- matrix
    typedef enum logic [1:0] {IDLE, WAVES, ROUTES, OUTS} state_t;
    state_t             state;
    logic [2:0]         k;      // route
    logic [1:0]         sub;    // 0: src * depth, 1: accumulate or x via, 2: accumulate
    logic signed [24:0] ma;
    logic signed [17:0] mb;
    logic signed [42:0] prod;
    logic signed [42:0] acc [5];
    assign prod = ma * mb;

    function automatic logic signed [17:0] source(input logic [3:0] s, input logic signed [17:0] l1,
                                                  input logic signed [17:0] l2, input logic signed [17:0] mw,
                                                  input logic signed [17:0] i1, input logic signed [17:0] i2,
                                                  input logic sy, input logic signed [17:0] ev,
                                                  input logic gt, input logic signed [17:0] ax,
                                                  input logic signed [17:0] fo);
        case (s)
            4'd1:    return l1;
            4'd2:    return l2;
            4'd3:    return mw;
            4'd4:    return i1;
            4'd5:    return i2;
            4'd6:    return sy ? ONE : -ONE;
            4'd7:    return ev;
            4'd8:    return gt ? ONE : '0;
            4'd9:    return ax;
            4'd10:   return fo;
            default: return '0;
        endcase
    endfunction

    function automatic logic signed [24:0] sat25(input logic signed [42:0] x);
        if (x > 43'sd16777215) return 25'sd16777215;
        if (x < -43'sd16777216) return -25'sd16777216;
        return x[24:0];
    endfunction

    function automatic logic signed [22:0] sat23(input logic signed [42:0] x);
        if (x > 43'sd4194303) return 23'sd4194303;
        if (x < -43'sd4194304) return -23'sd4194304;
        return x[22:0];
    endfunction

    // envelope follower, updated at tick
    logic signed [17:0] follow;
    wire  signed [17:0] fin   = fsrc ? in2 : in1;
    wire  signed [17:0] fabs  = fin == -18'sd131072 ? 18'sd131071 : (fin < 0 ? -fin : fin);
    wire  signed [18:0] fdiff = 19'(fabs) - 19'(follow);
    wire  signed [36:0] fprod = fdiff * $signed({1'b0, fabs > follow ? fatk : frel});

    // sources are sampled once per sample, at tick
    logic signed [17:0] in1_q, in2_q, env_q;
    logic               sync_q;
    wire signed [17:0]  src_k = source(r_src[k], lfo1, lfo2, modwheel, in1_q, in2_q, sync_q, env_q, gate, aux, follow);
    wire signed [17:0]  via_k = source(r_via[k], lfo1, lfo2, modwheel, in1_q, in2_q, sync_q, env_q, gate, aux, follow);
    wire signed [42:0]  am_sum = 43'(am_base) + acc[3];

    always_ff @(posedge clk) begin
        if (rst) begin
            ph[0] <= '0; ph[1] <= '0; rnd[0] <= '0; rnd[1] <= '0; rng <= 32'd1; follow <= '0;
            state <= IDLE; k <= '0; sub <= '0;
            lfo1 <= '0; lfo2 <= '0;
            pm <= '0; cm <= '0; am <= ONE; pw <= '0;
            for (int d = 0; d < 5; d++) acc[d] <= '0;
        end else begin
            case (state)
                IDLE: if (tick) begin
                    ph[0] <= (sync_edge && sreset[0]) ? '0 : nxt0[31:0];
                    ph[1] <= (sync_edge && sreset[1]) ? '0 : nxt1[31:0];
                    if (rng1 != rng) rnd[0] <= 18'($signed({2'b00, rng1[31:15]}) - 19'sd65536);
                    if (rng2 != rng1) rnd[1] <= 18'($signed({2'b00, rng2[31:15]}) - 19'sd65536);
                    rng    <= rng2;
                    in1_q  <= in1;
                    in2_q  <= in2;
                    follow <= 18'(19'(follow) + 19'(fprod >>> 16));
                    sync_q <= sync;
                    env_q  <= env;
                    for (int d = 0; d < 5; d++) acc[d] <= '0;
                    state  <= WAVES;
                end
                WAVES: begin
                    lfo1  <= lfo_wave(ph[0], wave[0], rnd[0]);
                    lfo2  <= lfo_wave(ph[1], wave[1], rnd[1]);
                    k     <= '0;
                    sub   <= '0;
                    state <= ROUTES;
                end
                ROUTES: begin
                    if (sub == 2'd0) begin
                        ma  <= 25'(r_depth[k]);
                        mb  <= src_k;
                        sub <= 2'd1;
                    end else if (sub == 2'd1 && r_via[k] != 4'd0) begin
                        ma  <= sat25(prod >>> 16);
                        mb  <= via_k;
                        sub <= 2'd2;
                    end else begin
                        acc[r_dst[k]] <= acc[r_dst[k]] + (prod >>> 16);
                        sub <= 2'd0;
                        k   <= k + 3'd1;
                        if (k == 3'd7) state <= OUTS;
                    end
                end
                OUTS: begin
                    pm    <= sat23(acc[1]);
                    cm    <= sat23(acc[2]);
                    am    <= am_sum > 43'sd131071 ? 18'sd131071 : am_sum < -43'sd131072 ? -18'sd131072 : 18'(am_sum);
                    pw    <= acc[4] > 43'sd65535 ? 17'sd65535 : acc[4] < -43'sd65536 ? -17'sd65536 : 17'(acc[4]);
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end

    assign gate_out = gate;

    wire unused = &{1'b0, wdata[31:24], addr[1:0], acc[0]};

endmodule

`default_nettype wire
