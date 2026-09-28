// Behavioural models for SoC testbenches: debug UART (monitor + scripted host)
// and a SPI NOR flash. Header-only, included by tb_audio.cpp with -DSOC.
#pragma once

#include <cstdint>
#include <functional>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

// Decodes 8N1 frames from the core's TX pin.
struct UartMonitor {
    double bit_cycles;
    bool busy = false;
    uint64_t start = 0;
    int nbit = 0;
    uint8_t byte = 0;
    int prev = 1;
    std::string text;
    uint64_t framing_errors = 0;

    explicit UartMonitor(double bc) : bit_cycles(bc) {}

    void step(uint64_t cyc, int tx) {
        if (!busy) {
            if (prev && !tx) {
                busy = true;
                start = cyc;
                nbit = 0;
                byte = 0;
            }
        } else {
            // sample in the middle of bit k (k = 0 start, 1..8 data, 9 stop)
            const uint64_t t = start + (uint64_t)((nbit + 0.5) * bit_cycles);
            if (cyc == t) {
                if (nbit >= 1 && nbit <= 8) byte |= (uint8_t)(tx << (nbit - 1));
                if (nbit == 9) {
                    if (!tx) ++framing_errors;
                    text.push_back((char)byte);
                    busy = false;
                }
                ++nbit;
            }
        }
        prev = tx;
    }
};

// Host side of the debug UART, driven by a script:
//   wait <text>        wait until the output (after the previous wait match) contains text
//   sendstr <text>     send ASCII
//   sendline <text>    send ASCII + "\n"
//   send <hex> ...     send bytes
//   sendfile <path>    send a file
//   delay <ms>
// Other commands go to the `ext` hook (panel models: pot / enc / btn).
struct UartHost {
    struct Cmd {
        std::string op, arg;
        int line;
    };
    std::vector<Cmd> cmds;
    size_t pc = 0;
    double bit_cycles;
    std::vector<uint8_t> queue;
    size_t qpos = 0;
    uint64_t byte_start = 0;
    bool sending = false;
    uint64_t delay_until = 0;
    size_t match_pos = 0;
    std::function<bool(const std::string&, const std::string&, uint64_t)> ext;

    UartHost(const std::string& path, double bc) : bit_cycles(bc) {
        if (path.empty()) return;
        std::ifstream f(path);
        if (!f) {
            fprintf(stderr, "cannot open UART script %s\n", path.c_str());
            exit(2);
        }
        std::string line;
        int n = 0;
        while (std::getline(f, line)) {
            ++n;
            if (line.empty() || line[0] == '#') continue;
            size_t sp = line.find(' ');
            cmds.push_back({line.substr(0, sp), sp == std::string::npos ? "" : line.substr(sp + 1), n});
        }
    }

    bool done() const { return pc >= cmds.size() && qpos >= queue.size() && !sending; }
    int line() const { return pc < cmds.size() ? cmds[pc].line : -1; }

    // Returns the RX pin level for this cycle.
    int step(uint64_t cyc, const std::string& out) {
        while (!sending && qpos >= queue.size() && pc < cmds.size() && cyc >= delay_until) {
            const Cmd& c = cmds[pc];
            if (c.op == "wait") {
                size_t p = out.find(c.arg, match_pos);
                if (p == std::string::npos) break;
                match_pos = p + c.arg.size();
            } else if (c.op == "sendstr" || c.op == "sendline") {
                queue.insert(queue.end(), c.arg.begin(), c.arg.end());
                if (c.op == "sendline") queue.push_back('\n');
            } else if (c.op == "send") {
                std::istringstream ss(c.arg);
                std::string tok;
                while (ss >> tok) queue.push_back((uint8_t)strtoul(tok.c_str(), nullptr, 16));
            } else if (c.op == "sendfile") {
                std::ifstream f(c.arg, std::ios::binary);
                if (!f) {
                    fprintf(stderr, "cannot open %s\n", c.arg.c_str());
                    exit(2);
                }
                queue.insert(queue.end(), std::istreambuf_iterator<char>(f), {});
            } else if (c.op == "delay") {
                delay_until = cyc + (uint64_t)(atof(c.arg.c_str()) * 1e-3 * SYS_CLK_HZ);
            } else if (!ext || !ext(c.op, c.arg, cyc)) {
                fprintf(stderr, "UART script line %d: unknown command %s\n", c.line, c.op.c_str());
                exit(2);
            }
            ++pc;
        }
        if (!sending && qpos < queue.size()) {
            sending = true;
            byte_start = cyc;
        }
        if (!sending) return 1;
        const int bit = (int)((cyc - byte_start) / bit_cycles);
        if (bit >= 10) {
            sending = false;
            ++qpos;
            return 1;
        }
        if (bit == 0) return 0;
        if (bit <= 8) return (queue[qpos] >> (bit - 1)) & 1;
        return 1;
    }
};

// SPI NOR flash, mode 0: 03 read, 02 page program, 20 4K erase, 06 WREN, 04 WRDI, 05 RDSR, 9F ID.
struct SpiFlash {
    static constexpr uint32_t SIZE = 16u << 20;
    std::vector<uint8_t> mem = std::vector<uint8_t>(SIZE, 0xFF);
    int prev_sck = 0, prev_cs = 1, miso = 0;
    int bitcnt = 0, nbytes = 0;
    uint8_t in = 0, out = 0, next_out = 0, cmd = 0;
    uint32_t addr = 0;
    bool wel = false;
    uint64_t programs = 0, erases = 0;

    void load(const std::string& path, uint32_t off) {
        std::ifstream f(path, std::ios::binary);
        if (!f) {
            fprintf(stderr, "cannot open flash image %s\n", path.c_str());
            exit(2);
        }
        std::vector<uint8_t> d((std::istreambuf_iterator<char>(f)), {});
        std::copy(d.begin(), d.end(), mem.begin() + off);
    }

    void dump(const std::string& path, uint32_t off, uint32_t len) const {
        FILE* f = fopen(path.c_str(), "wb");
        fwrite(mem.data() + off, 1, len, f);
        fclose(f);
    }

    void byte_in(uint8_t b) {
        ++nbytes;
        next_out = 0xFF;
        if (nbytes == 1) {
            cmd = b;
            addr = 0;
            if (cmd == 0x06) wel = true;
            if (cmd == 0x04) wel = false;
            if (cmd == 0x05) next_out = wel ? 0x02 : 0x00;
            if (cmd == 0x9F) next_out = 0xEF;
            return;
        }
        switch (cmd) {
        case 0x05: next_out = wel ? 0x02 : 0x00; break;
        case 0x9F: next_out = nbytes == 2 ? 0x40 : 0x18; break;
        case 0x03:
            if (nbytes <= 4) addr = (addr << 8) | b;
            if (nbytes >= 4) next_out = mem[addr++ % SIZE];
            break;
        case 0x02:
            if (nbytes <= 4) {
                addr = (addr << 8) | b;
            } else if (wel) {
                mem[addr % SIZE] &= b;
                addr = (addr & ~0xFFu) | ((addr + 1) & 0xFFu);
                ++programs;
            }
            break;
        case 0x20:
            if (nbytes <= 4) addr = (addr << 8) | b;
            break;
        default: break;
        }
    }

    // Returns MISO.
    int step(int sck, int mosi, int cs_n) {
        if (prev_cs && !cs_n) {
            bitcnt = nbytes = 0;
            next_out = 0xFF;
        }
        if (!prev_cs && cs_n) {  // end of command
            if (cmd == 0x20 && nbytes >= 4 && wel) {
                std::fill(mem.begin() + (addr & ~0xFFFu), mem.begin() + (addr & ~0xFFFu) + 4096, 0xFF);
                ++erases;
            }
            if ((cmd == 0x20 || cmd == 0x02) && nbytes >= 4) wel = false;
            cmd = 0;
        }
        if (!cs_n) {
            if (!prev_sck && sck) {
                in = (uint8_t)((in << 1) | (mosi & 1));
                if (++bitcnt == 8) {
                    byte_in(in);
                    bitcnt = 0;
                }
            }
            if (prev_sck && !sck) {
                if (bitcnt == 0) out = next_out;
                miso = (out >> (7 - bitcnt)) & 1;
            }
        }
        prev_sck = sck;
        prev_cs = cs_n;
        return miso;
    }
};

// MCP3208: 8 channels, values settable at run time. SPI mode 0, 24-clock frames.
struct Mcp3208 {
    uint16_t value[8] = {2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048};
    int prev_sck = 0, prev_cs = 1, miso = 1, nbit = 0, ch = 0;
    uint32_t in = 0;
    uint64_t frames = 0;

    int step(int sck, int mosi, int cs_n) {
        if (prev_cs && !cs_n) {
            nbit = 0;
            in = 0;
            miso = 1;
        }
        if (!cs_n) {
            if (!prev_sck && sck) {
                in = (in << 1) | (mosi & 1);
                ++nbit;
                if (nbit == 10) ch = in & 7;
                if (nbit == 24) ++frames;
            }
            if (prev_sck && !sck) {
                // after clock k (1-based) the device drives bit k+1: null bit at 12, B11..B0 at 13..24
                int k = nbit + 1;
                miso = k == 12 ? 0 : (k >= 13 && k <= 24) ? (value[ch] >> (24 - k)) & 1 : 1;
            }
        }
        prev_sck = sck;
        prev_cs = cs_n;
        return miso;
    }
};

// Rotary encoders (active low, idle high) and buttons; turns are queued and played out slowly
// enough for the debouncer (TRANSITION_US per quadrature step).
struct Encoders {
    static constexpr double TRANSITION_US = 400.0;
    struct Step {
        int enc, dir;
    };
    std::vector<Step> queue;
    size_t qpos = 0;
    int phase[4] = {0, 0, 0, 0};  // quadrature phase 0..3
    uint64_t next = 0;
    uint8_t btn = 0;              // pressed buttons (bit per encoder)
    uint64_t btn_release = 0;
    int a = 0xF, b = 0xF;

    void turn(int enc, int steps) {
        for (int i = 0; i < std::abs(steps) * 4; ++i) queue.push_back({enc, steps > 0 ? 1 : -1});
    }
    void press(int enc, uint64_t now) {
        btn |= (uint8_t)(1 << enc);
        btn_release = now + (uint64_t)(20e-3 * SYS_CLK_HZ);
    }
    void step(uint64_t cyc) {
        if (btn && cyc >= btn_release) btn = 0;
        if (qpos < queue.size() && cyc >= next) {
            const Step& s = queue[qpos++];
            phase[s.enc] = (phase[s.enc] + s.dir + 4) & 3;
            next = cyc + (uint64_t)(TRANSITION_US * 1e-6 * SYS_CLK_HZ);
        }
        static const int qa[4] = {0, 1, 1, 0}, qb[4] = {0, 0, 1, 1};  // A leads B clockwise
        a = b = 0xF;
        for (int k = 0; k < 4; ++k) {
            if (qa[phase[k]]) a &= ~(1 << k);
            if (qb[phase[k]]) b &= ~(1 << k);
        }
    }
    int sw() const { return 0xF & ~btn; }
};

// ST7789 in landscape: CASET = x, RASET = y, RAMWR pixel stream (RGB565, big endian).
struct St7789 {
    static constexpr int W = 320, H = 240;
    std::vector<uint16_t> fb = std::vector<uint16_t>(W * H, 0);
    int prev_sck = 0, prev_cs = 1, nbit = 0;
    uint8_t byte = 0, cmd = 0;
    int nargs = 0;
    uint16_t args[4];
    int xs = 0, xe = 0, ys = 0, ye = 0, x = 0, y = 0;
    bool hi = true;
    uint16_t pix = 0;
    uint64_t pixels = 0, commands = 0;
    bool on = false;

    void data(uint8_t d) {
        if (cmd == 0x2A || cmd == 0x2B) {
            if (nargs < 4) args[nargs++] = d;
            if (nargs == 4) {
                int lo = args[0] << 8 | args[1], hi2 = args[2] << 8 | args[3];
                if (cmd == 0x2A) xs = lo, xe = hi2;
                else ys = lo, ye = hi2;
            }
        } else if (cmd == 0x2C) {
            if (hi) {
                pix = (uint16_t)(d << 8);
                hi = false;
            } else {
                pix |= d;
                hi = true;
                if (x < W && y < H) fb[y * W + x] = pix;
                ++pixels;
                if (++x > xe) {
                    x = xs;
                    ++y;
                }
            }
        }
    }
    void command(uint8_t c) {
        cmd = c;
        nargs = 0;
        ++commands;
        if (c == 0x2C) {
            x = xs;
            y = ys;
            hi = true;
        }
        if (c == 0x29) on = true;
    }
    void step(int sck, int mosi, int cs_n, int dc) {
        if (prev_cs && !cs_n) nbit = 0;
        if (!cs_n && !prev_sck && sck) {
            byte = (uint8_t)((byte << 1) | (mosi & 1));
            if (++nbit == 8) {
                nbit = 0;
                if (dc) data(byte);
                else command(byte);
            }
        }
        prev_sck = sck;
        prev_cs = cs_n;
    }
    void dump(const std::string& path) const {
        FILE* f = fopen(path.c_str(), "wb");
        fwrite(fb.data(), 2, fb.size(), f);
        fclose(f);
    }
};

// Analog source for the AVK inputs, volts vs time: "off", "dc:V", "sine:F:A[:DC]", "square:F:A[:DC]",
// "saw:F:A[:DC]" (F in Hz, A amplitude in volts).
struct AnalogSource {
    enum Kind { DC, SINE, SQUARE, SAW } kind = DC;
    double f = 0, a = 0, dc = 0;

    bool parse(const std::string& spec) {
        char name[16] = {0};
        double v[3] = {0, 0, 0};
        int n = sscanf(spec.c_str(), "%15[a-z]:%lf:%lf:%lf", name, &v[0], &v[1], &v[2]);
        std::string k = name;
        if (k == "off" && n >= 1) *this = AnalogSource();
        else if (k == "dc" && n == 2) *this = AnalogSource{DC, 0, 0, v[0]};
        else if ((k == "sine" || k == "square" || k == "saw") && n >= 3)
            *this = AnalogSource{k == "sine" ? SINE : k == "square" ? SQUARE : SAW, v[0], v[1], n == 4 ? v[2] : 0};
        else return false;
        return true;
    }
    double volts(double t) const {
        double ph = f * t - std::floor(f * t);
        switch (kind) {
            case SINE: return dc + a * std::sin(2 * M_PI * ph);
            case SQUARE: return dc + (ph < 0.5 ? a : -a);
            case SAW: return dc + a * (2 * ph - 1);
            default: return dc;
        }
    }
};

// Two AD7091R (IN1, IN2) behind an ideal front end: -12.5..+12.5 V -> 0..4095. The input is
// sampled on the CONVST falling edge; MSB on SDO after the CS fall, next bits after SCLK falls.
struct Ad7091rPair {
    AnalogSource src[2];
    int code[2] = {2048, 2048}, sdo[2] = {0, 0};
    int prev_convst = 1, prev_cs = 1, prev_sclk = 0, bit = 11;
    uint64_t conversions = 0;

    static int to_code(double v) {
        double c = std::floor((v + 12.5) / 25.0 * 4096);
        return c < 0 ? 0 : c > 4095 ? 4095 : (int)c;
    }
    void step(double t, int convst_n, int cs_n, int sclk) {
        if (prev_convst && !convst_n) {
            for (int i = 0; i < 2; ++i) code[i] = to_code(src[i].volts(t));
            ++conversions;
        }
        if (prev_cs && !cs_n) bit = 11;
        else if (!cs_n && prev_sclk && !sclk && bit > 0) --bit;
        for (int i = 0; i < 2; ++i) sdo[i] = cs_n ? 0 : (code[i] >> bit) & 1;
        prev_convst = convst_n;
        prev_cs = cs_n;
        prev_sclk = sclk;
    }
};
