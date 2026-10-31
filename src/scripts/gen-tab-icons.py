# 生成底部 tab 图标：81×81 PNG，线性描边 1.8（按 24px 视口换算到 81px）
# 三个 tab：检查（盾牌+对勾）、广场（对话气泡）、我的（人像）
# 未选中 #8090A0，选中 #FFC93C（设计 token 的 $tab-off / $tab-on）
import os
from PIL import Image, ImageDraw

OUT = r"D:\qiuzhibilei\src\src\static\tab"
os.makedirs(OUT, exist_ok=True)

SIZE = 81
SCALE = SIZE / 24.0          # 设计稿按 24 视口画，放大到 81
STROKE = max(2, int(round(1.8 * SCALE)))

OFF_COLOR = (0x80, 0x90, 0xA0, 255)
ON_COLOR = (0xFF, 0xC9, 0x3C, 255)


def s(v):
    """设计稿坐标 -> 像素坐标"""
    return v * SCALE


def draw_check(d, color):
    # 盾牌：M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z（用折线近似）
    pts = [(12, 3), (19, 6), (19, 12), (18, 15), (15.5, 18), (12, 20.5),
           (8.5, 18), (6, 15), (5, 12), (5, 6), (12, 3)]
    d.line([(s(x), s(y)) for x, y in pts], fill=color, width=STROKE, joint="curve")
    # 对勾：M9 12l2 2 4-4
    d.line([(s(9), s(12)), (s(11), s(14)), (s(15), s(10))], fill=color, width=STROKE, joint="curve")


def draw_square(d, color):
    # 对话气泡：M21 12a8 8 0 01-11.6 7.1L4 20l1-4.4A8 8 0 1121 12z
    d.ellipse([s(4), s(4), s(20), s(20)], outline=color, width=STROKE)
    # 左下角小尾巴
    d.line([(s(9.4), s(19.1)), (s(4), s(20)), (s(4.9), s(14.6))], fill=color, width=STROKE, joint="curve")


def draw_mine(d, color):
    # 人头：circle cx12 cy8 r4
    d.ellipse([s(8), s(4), s(16), s(12)], outline=color, width=STROKE)
    # 肩膀：M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6
    pts = []
    for i in range(0, 21):
        t = i / 20.0
        x = 4 + t * 16
        # 二次曲线近似：control(12, 15) -> end(20, 21)
        y = (1 - t) ** 2 * 21 + 2 * (1 - t) * t * 15 + t ** 2 * 21
        pts.append((s(x), s(y)))
    d.line(pts, fill=color, width=STROKE, joint="curve")


ICONS = {
    "check": draw_check,
    "square": draw_square,
    "mine": draw_mine,
}

for name, fn in ICONS.items():
    for suffix, color in (("", OFF_COLOR), ("-on", ON_COLOR)):
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        fn(d, color)
        path = os.path.join(OUT, name + suffix + ".png")
        img.save(path)
        print("saved", path, img.size)
