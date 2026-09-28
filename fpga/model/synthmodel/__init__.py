"""Reference models of the AVK-6 FPGA synth DSP blocks (numpy).

Modules:
    clocks   -- sys_clk -> I2S/fs timing, NCO phase increments (bit-exact with RTL)
    nco      -- phase accumulator + quarter-wave sine table (bit-exact with RTL)
    adsr     -- exponential ADSR envelope (float reference)
    svf      -- state-variable filters: TPT/ZDF and Chamberlin (float reference)
    luts     -- generators of RTL tables (sine ROM)
    analysis -- spectrum, fundamental, THD, THD+N
    wavio    -- WAV read/write (16/24/32-bit PCM)
"""
