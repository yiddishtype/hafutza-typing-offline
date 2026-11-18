"""Draw the program's icon (a blue rounded square with a white Hebrew letter he and three text lines) -> .ico"""
import sys
from PIL import Image, ImageDraw, ImageFont
S = 256
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=48, fill=(30, 94, 168, 255))
try:
    f = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 150)
except OSError:
    f = ImageFont.load_default()
d.text((S // 2, 110), "\u05d4", font=f, fill="white", anchor="mm")
for i, w in enumerate((150, 120, 150)):
    y = 188 + i * 18
    d.rounded_rectangle([S - 48 - w, y, S - 48, y + 8], radius=4, fill=(255, 255, 255, 220))
im.save(sys.argv[1], sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
