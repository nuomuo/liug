#!/bin/bash
cd /home/yeeiee/pri/dida_mock/dida-clone
echo "=== package.json ==="
cat client/package.json
echo "=== api.js head ==="
head -20 client/src/api.js
echo "=== server static/branding ==="
grep -rn -i -E '滴答|dida|ticktick|static|dist' server/index.js | head -20
echo "=== generate wallpaper ==="
PROMPT='soft abstract wallpaper, flowing translucent silk waves in liquid glass style, pastel gradient of light blue, lavender and warm peach, smooth glossy surfaces, subtle light refraction, minimal elegant composition, macOS style desktop wallpaper, high resolution, no text'
ENC=$(python3 -c "import urllib.parse;print(urllib.parse.quote('''$PROMPT'''))")
curl -sL -o client/public/bg.jpg "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=${ENC}&image_size=landscape_16_9"
file client/public/bg.jpg
ls -la client/public/
