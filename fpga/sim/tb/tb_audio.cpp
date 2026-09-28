// Generic Verilator testbench for audio cores with the common port set
// (clk, rst, midi_rx, i2s_bck, i2s_lrck, i2s_din). Build with
//   -DTOP_CLASS=Vmono_core -DTOP_HEADER='"Vmono_core.h"' -DSYS_CLK_HZ=... -DDATA_W=...
//   -DMIDI_ECHO   the core exports midi_data/midi_valid: received bytes are checked
//   -DSOC         CPU core (synth_core): debug UART monitor + scripted host, SPI flash model,
//                 trap check; options --uart-out --uart-script --stop-on --flash-image
//                 --flash-dump; UART_BAUD must be defined
//
// Drives midi_rx from a MIDI stimulus file at 31250 baud, decodes the I2S pins as a
// DAC would (sampling DIN on BCK rising edges) and checks the frame format:
//   - LRCK/DIN change only together with a BCK falling edge;
//   - 32 BCK per LRCK half, 64 per frame; constant BCK half-period;
//   - bits below DATA_W in each 32-bit slot are zero.
// Writes a stereo 24-bit WAV and a JSON summary; exit code 1 on format/MIDI errors.
// Audio content is checked by the pytest system tests (fpga/sim/system/).
//
// Usage: tb_audio --duration S --wav out.wav --json out.json [--midi stim.txt]
//
// MIDI stimulus format (text): "<time_ms> <hex byte> [<hex byte> ...]" per line,
// '#' starts a comment. Bytes are sent back to back from time_ms (or after the
// previous message, whichever is later).

#include TOP_HEADER
#include "verilated.h"

#include <cinttypes>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#ifdef SOC
#include "soc_models.h"
#endif

#ifndef TOP_CLASS
#error "define TOP_CLASS / TOP_HEADER"
#endif
#ifndef SYS_CLK_HZ
#error "define SYS_CLK_HZ to match the RTL parameter"
#endif
#ifndef DATA_W
#error "define DATA_W to match the RTL parameter"
#endif

static constexpr double MIDI_BAUD = 31250.0;
static constexpr int SLOT_BITS = 32;
static constexpr int WAV_BITS = 24;

struct MidiByte {
    uint64_t start_cycle;
    uint8_t value;
};

static std::vector<MidiByte> load_midi(const std::string& path, double bit_cycles) {
    std::vector<MidiByte> out;
    std::ifstream f(path);
    if (!f) {
        fprintf(stderr, "cannot open MIDI stimulus %s\n", path.c_str());
        exit(2);
    }
    std::string line;
    uint64_t next_free = 0;
    int lineno = 0;
    while (std::getline(f, line)) {
        ++lineno;
        line = line.substr(0, line.find('#'));
        std::istringstream ss(line);
        double t_ms;
        if (!(ss >> t_ms)) continue;
        uint64_t t = (uint64_t)llround(t_ms * 1e-3 * SYS_CLK_HZ);
        if (t < next_free) t = next_free;
        std::string tok;
        while (ss >> tok) {
            char* end = nullptr;
            unsigned long v = strtoul(tok.c_str(), &end, 16);
            if (*end || v > 0xff) {
                fprintf(stderr, "%s:%d: bad byte '%s'\n", path.c_str(), lineno, tok.c_str());
                exit(2);
            }
            out.push_back({t, (uint8_t)v});
            t += (uint64_t)llround(10 * bit_cycles);
        }
        next_free = t;
    }
    return out;
}

// Level of the MIDI line (UART, idle high) at a given cycle.
struct MidiDriver {
    const std::vector<MidiByte>& bytes;
    double bit_cycles;
    size_t idx = 0;

    int level(uint64_t cyc) {
        while (idx < bytes.size() && cyc >= bytes[idx].start_cycle + (uint64_t)llround(10 * bit_cycles))
            ++idx;
        if (idx >= bytes.size() || cyc < bytes[idx].start_cycle) return 1;
        int bit = (int)((cyc - bytes[idx].start_cycle) / bit_cycles);
        if (bit == 0) return 0;               // start
        if (bit <= 8) return (bytes[idx].value >> (bit - 1)) & 1;  // LSB first
        return 1;                             // stop
    }
};

struct I2sDecoder {
    bool started = false;
    int lrck = 0;
    std::vector<int> bits;
    bool have_left = false;
    int32_t left = 0;
    std::vector<int32_t> out_l, out_r;
    std::vector<uint64_t> frame_cycles;
    uint64_t errors = 0, pad_errors = 0;
    std::string first_error;

    void error(const std::string& msg, bool pad = false) {
        (pad ? pad_errors : errors)++;
        if (first_error.empty()) first_error = msg;
    }

    void finish_slot(int ch, uint64_t cyc) {
        if ((int)bits.size() != SLOT_BITS) {
            error("slot length " + std::to_string(bits.size()) + " at cycle " + std::to_string(cyc));
            have_left = false;
            return;
        }
        int32_t v = 0;
        for (int i = 0; i < DATA_W; ++i) v = (v << 1) | bits[i];
        if (v & (1 << (DATA_W - 1))) v -= (1 << DATA_W);  // sign extend
        for (int i = DATA_W; i < SLOT_BITS; ++i)
            if (bits[i]) {
                error("non-zero pad bit at cycle " + std::to_string(cyc), true);
                break;
            }
        if (ch == 0) {
            left = v;
            have_left = true;
        } else if (have_left) {
            out_l.push_back(left);
            out_r.push_back(v);
            frame_cycles.push_back(cyc);
            have_left = false;
        }
    }

    // Called on each BCK rising edge with the sampled LRCK and DIN.
    void rise(int lr, int din, uint64_t cyc) {
        if (!started) {
            if (lr != lrck) started = true;  // first LRCK edge: start of a clean slot
            lrck = lr;
            bits.clear();
            return;
        }
        if (lr != lrck) {
            // I2S: the first bit after an LRCK edge is the LSB of the previous slot
            bits.push_back(din);
            finish_slot(lrck, cyc);
            bits.clear();
            lrck = lr;
        } else {
            bits.push_back(din);
        }
    }
};

static void write_wav(const std::string& path, uint32_t fs, const std::vector<int32_t>& l,
                      const std::vector<int32_t>& r) {
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) {
        fprintf(stderr, "cannot write %s\n", path.c_str());
        exit(2);
    }
    const uint16_t ch = 2, bps = WAV_BITS / 8, align = ch * bps;
    const uint32_t data_len = (uint32_t)l.size() * align;
    auto u32 = [&](uint32_t v) { fwrite(&v, 4, 1, f); };
    auto u16 = [&](uint16_t v) { fwrite(&v, 2, 1, f); };
    fwrite("RIFF", 1, 4, f); u32(36 + data_len); fwrite("WAVE", 1, 4, f);
    fwrite("fmt ", 1, 4, f); u32(16); u16(1); u16(ch); u32(fs); u32(fs * align); u16(align);
    u16(WAV_BITS);
    fwrite("data", 1, 4, f); u32(data_len);
    for (size_t i = 0; i < l.size(); ++i) {
        for (int32_t s : {l[i], r[i]}) {
            int32_t v = s * (1 << (WAV_BITS - DATA_W));
            uint8_t b[3] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16)};
            fwrite(b, 1, 3, f);
        }
    }
    fclose(f);
}

int main(int argc, char** argv) {
    double duration = 0.3;
    std::string midi_path, wav_path = "stub.wav", json_path = "stub.json";
    std::string uart_out, uart_script, stop_on, flash_image, flash_dump;
    uint32_t flash_image_off = 0, flash_dump_off = 0, flash_dump_len = 0;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) {
                fprintf(stderr, "%s needs a value\n", a.c_str());
                exit(2);
            }
            return argv[++i];
        };
        if (a == "--duration") duration = atof(next().c_str());
        else if (a == "--midi") midi_path = next();
        else if (a == "--wav") wav_path = next();
        else if (a == "--json") json_path = next();
        else if (a == "--uart-out") uart_out = next();
        else if (a == "--uart-script") uart_script = next();
        else if (a == "--stop-on") stop_on = next();
        else if (a == "--flash-image") {  // path@offset
            std::string v = next();
            size_t at = v.find('@');
            flash_image = v.substr(0, at);
            flash_image_off = at == std::string::npos ? 0 : (uint32_t)strtoul(v.c_str() + at + 1, nullptr, 0);
        } else if (a == "--flash-dump") {  // path@offset+len
            std::string v = next();
            size_t at = v.find('@'), plus = v.find('+');
            flash_dump = v.substr(0, at);
            flash_dump_off = (uint32_t)strtoul(v.c_str() + at + 1, nullptr, 0);
            flash_dump_len = (uint32_t)strtoul(v.c_str() + plus + 1, nullptr, 0);
        }
        else if (a[0] != '+') {  // +verilator+... plusargs are passed through
            fprintf(stderr, "unknown argument %s\n", a.c_str());
            return 2;
        }
    }

    const double bit_cycles = SYS_CLK_HZ / MIDI_BAUD;
    std::vector<MidiByte> midi;
    if (!midi_path.empty()) midi = load_midi(midi_path, bit_cycles);
    MidiDriver drv{midi, bit_cycles};

    auto ctx = std::make_unique<VerilatedContext>();
    ctx->commandArgs(argc, argv);
    auto top = std::make_unique<TOP_CLASS>(ctx.get());

    const uint64_t total = (uint64_t)(duration * SYS_CLK_HZ);
    const uint64_t reset_cycles = 16;
    I2sDecoder dec;
    std::vector<uint8_t> midi_rx_bytes;
    uint64_t timing_errors = 0, half_min = UINT64_MAX, half_max = 0, last_bck_edge = 0;
    int prev_bck = 0, prev_lrck = 0, prev_din = 0;
    std::string first_timing_error;

#ifdef SOC
    const double uart_bit = (double)SYS_CLK_HZ / UART_BAUD;
    UartMonitor mon(uart_bit);
    UartHost host(uart_script, uart_bit);
    SpiFlash flash;
    if (!flash_image.empty()) flash.load(flash_image, flash_image_off);
    bool trapped = false, stopped = false;
    top->uart_rx = 1;
    top->btn = 0;
    top->flash_miso = 1;
#endif

    top->rst = 1;
    top->midi_rx = 1;
    top->clk = 0;
    top->eval();
    uint64_t cyc = 0;
    for (; cyc < total; ++cyc) {
        top->rst = cyc < reset_cycles;
        top->midi_rx = cyc < reset_cycles ? 1 : drv.level(cyc - reset_cycles);
#ifdef SOC
        top->uart_rx = host.step(cyc, mon.text);
        top->flash_miso = flash.step(top->flash_sck, top->flash_mosi, top->flash_cs_n);
#endif
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
        if (cyc < reset_cycles) continue;

        const int bck = top->i2s_bck, lrck = top->i2s_lrck, din = top->i2s_din;
        const bool fall = prev_bck && !bck, rise = !prev_bck && bck;
        if ((lrck != prev_lrck || din != prev_din) && !fall) {
            if (!timing_errors++)
                first_timing_error = "LRCK/DIN changed without BCK fall at cycle " + std::to_string(cyc);
        }
        if (fall || rise) {
            if (last_bck_edge) {
                uint64_t h = cyc - last_bck_edge;
                if (h < half_min) half_min = h;
                if (h > half_max) half_max = h;
            }
            last_bck_edge = cyc;
        }
        if (rise) dec.rise(lrck, din, cyc);
#ifdef MIDI_ECHO
        if (top->midi_valid) midi_rx_bytes.push_back(top->midi_data);
#endif
#ifdef SOC
        mon.step(cyc, top->uart_tx);
        if (top->trap) {
            trapped = true;
            break;
        }
        if (!stop_on.empty() && host.done() && (cyc & 1023) == 0 && mon.text.find(stop_on) != std::string::npos) {
            stopped = true;
            break;
        }
#endif
        prev_bck = bck;
        prev_lrck = lrck;
        prev_din = din;
    }
    top->final();

    // Bytes whose stop bit ended before the end of the run must have been received.
    size_t expected = 0;
    for (const auto& b : midi)
        if (b.start_cycle + (uint64_t)llround(10 * bit_cycles) + reset_cycles < cyc) ++expected;
#ifdef MIDI_ECHO
    bool midi_ok = midi_rx_bytes.size() == expected;
    for (size_t i = 0; midi_ok && i < expected; ++i) midi_ok = midi_rx_bytes[i] == midi[i].value;
#else
    const bool midi_ok = true;
#endif

    double fs = 0;
    const size_t nf = dec.frame_cycles.size();
    if (nf > 1)
        fs = SYS_CLK_HZ * (double)(nf - 1) / (double)(dec.frame_cycles[nf - 1] - dec.frame_cycles[0]);
    if (half_min != half_max) {
        ++timing_errors;
        if (first_timing_error.empty()) first_timing_error = "BCK half-period not constant";
    }
    if (nf < 2) dec.error("fewer than 2 frames decoded");
#ifdef SOC
    if (!uart_out.empty()) {
        std::ofstream(uart_out, std::ios::binary) << mon.text;
    }
    if (!flash_dump.empty()) flash.dump(flash_dump, flash_dump_off, flash_dump_len);
    std::string soc_error;
    if (trapped) soc_error = "CPU trap at cycle " + std::to_string(cyc);
    else if (!host.done()) soc_error = "UART script stuck at line " + std::to_string(host.line());
    else if (!stop_on.empty() && !stopped) soc_error = "stop text not seen: " + stop_on;
    else if (mon.framing_errors) soc_error = "UART framing errors";
    if (!soc_error.empty()) dec.error(soc_error);
#endif

    write_wav(wav_path, (uint32_t)llround(fs > 0 ? fs : 48000), dec.out_l, dec.out_r);

    const bool ok = !dec.errors && !dec.pad_errors && !timing_errors && midi_ok;
    std::string first = !dec.first_error.empty() ? dec.first_error : first_timing_error;
    for (char& ch : first)
        if (ch == '"' || ch == '\\') ch = '\'';
    FILE* j = fopen(json_path.c_str(), "w");
    if (!j) {
        fprintf(stderr, "cannot write %s\n", json_path.c_str());
        return 2;
    }
    fprintf(j,
            "{\n  \"sys_clk_hz\": %d,\n  \"data_w\": %d,\n  \"duration_s\": %g,\n"
            "  \"fs_hz\": %.6f,\n  \"frames\": %zu,\n  \"bck_half_cycles\": [%" PRIu64 ", %" PRIu64 "],\n"
            "  \"i2s_errors\": %" PRIu64 ",\n  \"pad_errors\": %" PRIu64 ",\n  \"timing_errors\": %" PRIu64 ",\n"
            "  \"midi_sent\": %zu,\n  \"midi_received\": %zu,\n  \"midi_ok\": %s,\n"
            "  \"first_frame_cycle\": %" PRIu64 ",\n  \"reset_cycles\": %" PRIu64 ",\n"
            "  \"cycles\": %" PRIu64 ",\n"
            "  \"first_error\": \"%s\",\n  \"ok\": %s\n}\n",
            (int)SYS_CLK_HZ, DATA_W, duration, fs, nf, half_min, half_max, dec.errors, dec.pad_errors,
            timing_errors, expected, midi_rx_bytes.size(), midi_ok ? "true" : "false",
            nf ? dec.frame_cycles[0] : (uint64_t)0, reset_cycles, cyc, first.c_str(),
            ok ? "true" : "false");
    fclose(j);

    printf("tb_audio: %zu frames, fs = %.3f Hz, I2S errors %" PRIu64 ", pad %" PRIu64 ", timing %" PRIu64
           ", MIDI %zu/%zu %s -> %s\n",
           nf, fs, dec.errors, dec.pad_errors, timing_errors, midi_rx_bytes.size(), expected,
           midi_ok ? "ok" : "MISMATCH", ok ? "PASS" : "FAIL");
    if (!first.empty()) printf("  first error: %s\n", first.c_str());
    return ok ? 0 : 1;
}
