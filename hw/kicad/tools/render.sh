#!/bin/sh
# Экспорт листов в SVG/PNG для просмотра: render.sh <каталог>
set -e
D=${1:-/tmp/avk_render}
mkdir -p "$D"
cd "$(dirname "$0")/.."
kicad-cli sch export svg -o "$D" avk_synth.kicad_sch >/dev/null
python3 -c "
import cairosvg, glob, sys
for f in glob.glob('$D/*.svg'):
    cairosvg.svg2png(url=f, write_to=f[:-4] + '.png', output_width=2400, background_color='white')
"
ls "$D"/*.png
