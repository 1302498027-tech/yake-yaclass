# -*- coding: utf-8 -*-
"""Sprout 绿芽 · 应用图标生成（绿色圆角方块 + 白色嫩芽）"""
import os
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "icon")
os.makedirs(OUT, exist_ok=True)

S = 512  # 先画大图再缩小，保证边缘平滑

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# ---- 背景：垂直渐变绿色圆角方块 ----
R = int(S * 0.225)  # 圆角半径
top = (58, 138, 255)    # #3a8aff
bot = (23, 84, 200)     # #1754c8
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=R, fill=255)
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
for y in range(S):
    t = y / (S - 1)
    c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,)
    gd.line([(0, y), (S, y)], fill=c)
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)

W = (255, 255, 255, 255)

# ---- 茎：从底部中央向上的圆头竖线 ----
stem_x = S // 2
stem_top = int(S * 0.40)
stem_bot = int(S * 0.74)
stem_w = int(S * 0.045)
d.line([(stem_x, stem_top), (stem_x, stem_bot)], fill=W, width=stem_w)
r = stem_w // 2
d.ellipse([stem_x - r, stem_bot - r, stem_x + r, stem_bot + r], fill=W)

# ---- 两片叶子：椭圆旋转后贴上 ----
def leaf(cx, cy, angle, w, h):
    lw, lh = int(w), int(h)
    pad = int(max(lw, lh) * 0.8)
    tile = Image.new("RGBA", (lw + pad * 2, lh + pad * 2), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.ellipse([pad, pad, pad + lw, pad + lh], fill=W)
    tile = tile.rotate(angle, resample=Image.BICUBIC, expand=True)
    px = int(cx - tile.width / 2)
    py = int(cy - tile.height / 2)
    img.alpha_composite(tile, (px, py))

# 叶子以茎顶为交点，左右张开
leaf(int(S * 0.315), int(S * 0.335), -28, int(S * 0.30), int(S * 0.115))
leaf(int(S * 0.685), int(S * 0.335), 28, int(S * 0.30), int(S * 0.115))

# ---- 256 PNG ----
p256 = img.resize((256, 256), Image.LANCZOS)
p256.save(os.path.join(OUT, "sprout_256.png"))

# ---- ICO（多尺寸）----
p256.save(
    os.path.join(OUT, "sprout.ico"),
    sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
)
print("icon saved:", os.path.join(OUT, "sprout_256.png"))
print("icon saved:", os.path.join(OUT, "sprout.ico"))
