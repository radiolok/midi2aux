// Behavioural models for SoC testbenches: debug UART (monitor + scripted host)
// and a SPI NOR flash. Header-only, included by tb_audio.cpp with -DSOC.
#pragma once

#include <cstdint>
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
//   send <hex> ...     send bytes
//   sendfile <path>    send a file
//   delay <ms>
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
            } else if (c.op == "sendstr") {
                queue.insert(queue.end(), c.arg.begin(), c.arg.end());
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
            } else {
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
