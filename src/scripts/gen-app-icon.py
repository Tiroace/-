# 生成小程序图标（提审视觉三件套之一，D38 个人主体 / 工具类口径）
#
# 设计口径：
#   - 工具类，简洁可识别，不用文字（微信图标里放小字在 144px 下糊成一团）
#   - 图形沿用 tab 栏「检查」的盾牌 + 对勾，保证和产品内部视觉一致
#   - 配色取 uni.scss 的品牌 token：底色 $bg #0e1620、图形 $cta #ffc93c
#   - 大尺寸加一层浅黄描边与内发光，缩到 144px 仍清楚；小尺寸自动加粗线条
#
# 输出（全部 PNG，RGBA 之外另存一份不透明版备提审）：
#   icon-1024.png / icon-512.png / icon-216.png / icon-144.png / icon-135.png / icon-81.png
#   icon-round-1024.png（圆角版，用于需要圆角的场景）
#
# 用法：python src/scripts/gen-app-icon.py
import os
from PIL import Image, ImageDraw, ImageFilter

ROOT = r"D:\qiuzhibilei"
OUT = os.path.join(ROOT, "src", "src", "static", "app-icon")

# 品牌 token（与 uni.scss 保持一致）
BG = (0x0E, 0x16, 0x20, 255)      # $bg
BRAND = (0xFF, 0xC9, 0x3C, 255)   # $cta
BRAND_SOFT = (0xFF, 0xC9, 0x3C, 60)

SIZES = [1024, 512, 216, 144, 135, 81]

# 设计稿视口 24，和 gen-tab-icons.py 一致
VIEW = 24.0


def shield_points():
    """盾牌折线，视口 24 坐标。
    注意：首点不要重复收尾（(12,3) 出现两次会让闭合处被画成缺口），
    要闭合就让 draw 时显式接回起点。"""
    return [(12, 3), (19, 6), (19, 12), (18, 15), (15.5, 18), (12, 20.5),
            (8.5, 18), (6, 15), (5, 12), (5, 6)]


def check_points():
    """对勾，视口 24 坐标"""
    return [(9, 12), (11, 14), (15, 10)]


def render(size: int, rounded: bool = False) -> Image.Image:
    """按目标尺寸渲染。线条粗细随尺寸调，保证小图标不糊。"""
    # 4 倍超采样再缩，抗锯齿更干净
    ss = 4
    px = size * ss
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    scale = px / VIEW

    def s(v):
        return v * scale

    # 1) 底色：圆角矩形（微信图标本身建议直角，这里默认直角，圆角版另出）
    if rounded:
        radius = int(px * 0.22)
    else:
        radius = 0
    d.rounded_rectangle([0, 0, px - 1, px - 1], radius=radius, fill=BG)

    # 2) 图形区居中：视口内容约 24x24，但盾牌实际占 3..20.5，
    #    缩进让图形视觉居中（顶距小一点、底距大一点，视觉重心才正）
    pad = px * 0.145

    def map_pt(x, y):
        """把 24 视口坐标映射到留白后的图形区"""
        vx = pad + (x / VIEW) * (px - 2 * pad)
        vy = pad + (y / VIEW) * (px - 2 * pad)
        return (vx, vy)

    # 线条宽度：大图标细一点显精致，小图标必须粗，否则糊
    if size >= 512:
        stroke_ratio = 1.55 / VIEW
    elif size >= 144:
        stroke_ratio = 1.85 / VIEW
    else:
        stroke_ratio = 2.35 / VIEW
    # 线宽按「实际绘制区域」算，确保不同尺寸下视觉粗细一致
    w = max(int((px - 2 * pad) * stroke_ratio), 2)

    # 3) 内发光：先画一层半透明粗线，再模糊，营造灯牌感
    #    盾牌要闭合，这里显式把起点接回末尾
    shield = shield_points() + [shield_points()[0]]
    glow = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.line([map_pt(x, y) for x, y in shield], fill=BRAND_SOFT,
            width=w * 3, joint="curve")
    gd.line([map_pt(x, y) for x, y in check_points()], fill=BRAND_SOFT,
            width=w * 3, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(1, int(px * 0.012))))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    # 4) 盾牌 + 对勾：品牌黄实线
    #    盾牌用 polygon 画闭合轮廓再「挖空」不划算，这里改成逐段画线 +
    #    在每个顶点补一个圆点，顶点处永远是圆的，不会出现 joint 造成的缺口。
    pts = [map_pt(x, y) for x, y in shield_points()]
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]  # 最后一段接回首点，形成闭合
        d.line([a, b], fill=BRAND, width=w)
        r = w / 2.0
        d.ellipse([a[0] - r, a[1] - r, a[0] + r, a[1] + r], fill=BRAND)
    cpts = [map_pt(x, y) for x, y in check_points()]
    for i in range(len(cpts) - 1):
        d.line([cpts[i], cpts[i + 1]], fill=BRAND, width=w)
    for p in cpts:
        r = w / 2.0
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=BRAND)

    # 5) 缩小到目标尺寸
    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    outputs = []
    for size in SIZES:
        im = render(size)
        p = os.path.join(OUT, "icon-%d.png" % size)
        im.save(p)
        outputs.append((p, size, os.path.getsize(p)))

    # 圆角版（部分场景如应用商店需要圆角）
    im = render(1024, rounded=True)
    p = os.path.join(OUT, "icon-round-1024.png")
    im.save(p)
    outputs.append((p, 1024, os.path.getsize(p)))

    # 微信小程序后台「图标」推荐上传 144x144（PNG），单独放一份到根目录方便找
    import shutil
    shutil.copyfile(os.path.join(OUT, "icon-144.png"),
                    os.path.join(ROOT, "src", "src", "static", "app-icon-144.png"))
    p144 = os.path.join(ROOT, "src", "src", "static", "app-icon-144.png")
    outputs.append((p144, 144, os.path.getsize(p144)))

    print("生成目录：", OUT)
    for p, size, n in outputs:
        print("  %-8s %6d bytes  %s" % (str(size) + "px", n, p))

    # 自检：尺寸与格式
    print("\n自检：")
    ok = True
    for size in SIZES:
        im = Image.open(os.path.join(OUT, "icon-%d.png" % size))
        good = im.size == (size, size) and im.format == "PNG"
        ok = ok and good
        print("  %s icon-%d.png 尺寸=%s 格式=%s" % ("✓" if good else "✗", size, im.size, im.format))
    print("\n" + ("全部通过" if ok else "有失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
