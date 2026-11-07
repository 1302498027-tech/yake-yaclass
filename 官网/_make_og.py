# -*- coding: utf-8 -*-
"""生成 1200x630 社交分享卡 og.png（与站点同一套配色）"""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
INK = (35, 31, 32)
CREAM = (240, 237, 221)
ACCENT = (255, 69, 18)
GREY = (168, 164, 152)

SERIF = r"C:\Windows\Fonts\NotoSerifSC-VF.ttf"
SANS = r"C:\Windows\Fonts\msyhl.ttc"


def font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        return ImageFont.truetype(r"C:\Windows\Fonts\simsun.ttc", size, index=0)


img = Image.new("RGB", (W, H), INK)
d = ImageDraw.Draw(img)

# 右上角三个点（品牌标记）
for i, (dx, dy, r) in enumerate([(0, 4, 4), (14, 1, 6), (30, 4, 4)]):
    color = ACCENT if i == 2 else CREAM
    cx, cy = W - 96 + dx, 78 + dy
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

# 顶部小标
f_lab = font(SANS, 22)
d.text((96, 64), "Y A C L A S S", font=f_lab, fill=(200, 196, 184))

# 主张：两行
f_big = font(SERIF, 126)
y1, y2 = 158, 296
d.text((92, y1), "读完，", font=f_big, fill=CREAM)
d.text((92, y2), "不算。", font=f_big, fill=ACCENT)

# 分隔线
d.line([(96, 516), (W - 96, 516)], fill=(64, 60, 60), width=1)

# 底部信息
f_small = font(SANS, 26)
d.text((96, 546), "6 个模块 · 193 格 · 一天一格 · 只认你写下的那一句", font=f_small, fill=GREY)
en = "A learning system with proof."
w_en = d.textlength(en, font=f_small)
d.text((W - 96 - w_en, 546), en, font=f_small, fill=(120, 116, 108))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "og.png")
img.save(out, "PNG", optimize=True)
print("saved", out, os.path.getsize(out), "bytes")
