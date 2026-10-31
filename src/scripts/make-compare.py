# 把设计稿渲染图拼成一张对比图（设计稿侧）。小程序侧截图由测试者补齐后可用同脚本再拼一次。
# 用法：python miniprogram/scripts/make-compare.py
import os
from PIL import Image, ImageDraw, ImageFont

BASE = r"D:\qiuzhibilei\reports\rebrand"
DESIGN = os.path.join(BASE, "design")
OUT = os.path.join(BASE, "对比-设计稿.png")

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
font_title = ImageFont.truetype(FONT_PATH, 34) if os.path.exists(FONT_PATH) else None

PAGES = [
    ("01-首页.png", "首页"),
    ("05-我的.png", "我的"),
    ("04-会员页.png", "会员"),
    ("03-次数用完弹窗.png", "次数用完弹窗"),
]

# 统一缩放宽度，避免不同高度差太多
TARGET_W = 390
GAP = 28
LABEL_H = 56

imgs = []
for fn, label in PAGES:
    p = os.path.join(DESIGN, fn)
    if not os.path.exists(p):
        print("跳过（不存在）", p)
        continue
    im = Image.open(p).convert("RGB")
    w, h = im.size
    nh = int(h * TARGET_W / w)
    imgs.append((im.resize((TARGET_W, nh), Image.LANCZOS), label))

if not imgs:
    raise SystemExit("没有可用的设计稿渲染图")

total_w = sum(im.width for im, _ in imgs) + GAP * (len(imgs) - 1)
max_h = max(im.height for im, _ in imgs)
canvas = Image.new("RGB", (total_w, max_h + LABEL_H), (14, 22, 32))
draw = ImageDraw.Draw(canvas)

x = 0
for im, label in imgs:
    canvas.paste(im, (x, LABEL_H))
    if font_title:
        draw.text((x + 12, 12), "设计稿 · " + label, fill=(241, 244, 246), font=font_title)
    x += im.width + GAP

canvas.save(OUT)
print("已生成：", OUT, canvas.size)
