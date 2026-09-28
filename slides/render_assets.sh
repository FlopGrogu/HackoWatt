#!/bin/sh
# Renders the slide assets in slides/assets/source.html to transparent PNGs (2x resolution) in slides/assets/.
# Needs Google Chrome. Usage: sh slides/render_assets.sh
cd "$(dirname "$0")/assets" || exit 1
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for spec in diagram:1000x545:model_diagram timeline:1000x300:timeline_22sep result:1000x330:result; do
  asset=${spec%%:*}; rest=${spec#*:}; size=${rest%%:*}; name=${rest#*:}
  for theme in dark light; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
      --default-background-color=00000000 --virtual-time-budget=3000 \
      --window-size="$(echo "$size" | tr x ,)" \
      --screenshot="$PWD/${name}_${theme}.png" "file://$PWD/source.html?asset=$asset&theme=$theme" 2>/dev/null
    echo "slides/assets/${name}_${theme}.png"
  done
done
# wide diagram in the style of the team's slide template (transparent, for the beige background)
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --default-background-color=00000000 --virtual-time-budget=3000 --window-size=1500,545 \
  --screenshot="$PWD/model_diagram_slide.png" "file://$PWD/source.html?asset=wide" 2>/dev/null
echo "slides/assets/model_diagram_slide.png"
# levers slide (where the kWh go), same style
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --default-background-color=00000000 --virtual-time-budget=3000 --window-size=1500,560 \
  --screenshot="$PWD/levers_slide.png" "file://$PWD/source.html?asset=levers" 2>/dev/null
echo "slides/assets/levers_slide.png"
