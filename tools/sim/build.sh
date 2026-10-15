#!/bin/sh
# Build host simulations of the poly engine: tools/sim/build.sh [outdir]
set -e
D=$(cd "$(dirname "$0")" && pwd); S="$D/../../fw/src"; O=${1:-$D/out}; mkdir -p "$O"
for nv in 1 4; do
	g++ -O1 -Wall -Wno-unused-function -I"$D" -DF_CPU=16000000L -DPOLY_VOICES=$nv -DSINE_ENV \
		"$D/sim.cpp" "$D/regs.cpp" "$S/poly.cpp" "$S/envelope.cpp" "$S/midi.cpp" "$S/waveform.cpp" \
		-o "$O/sim_poly$nv" -lm
done
# main.cpp: compile-only check of both ADC variants
for d in "" "-DPOT2_ADC=6"; do
	g++ -fsyntax-only -Wall -I"$D" -DF_CPU=16000000L -DPOLY_VOICES=4 -DSINE_ENV $d "$S/main.cpp"
done
