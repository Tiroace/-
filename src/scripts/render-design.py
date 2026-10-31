# 用本机 Edge 无头模式把设计稿参考 HTML 渲染成图片，作为并排对比的「设计稿侧」。
# 用法：python miniprogram/scripts/render-design.py
import os
import subprocess
import sys

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SRC = r"D:\qiuzhibilei\design\改版包-20261030\面试请等等-改版包\03-参考代码"
OUT = r"D:\qiuzhibilei\reports\rebrand\design"
os.makedirs(OUT, exist_ok=True)

PAGES = [
    ("01-首页.html", "01-首页.png", 390, 1200),
    ("03-次数用完弹窗.html", "03-次数用完弹窗.png", 390, 844),
    ("04-会员页.html", "04-会员页.png", 390, 1010),
    ("05-我的.html", "05-我的.png", 390, 930),
]


def shot(html, png, w, h):
    url = "file:///" + os.path.join(SRC, html).replace("\\", "/")
    out = os.path.join(OUT, png)
    args = [
        EDGE,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=2",
        "--window-size=%d,%d" % (w, h),
        "--screenshot=" + out,
        url,
    ]
    r = subprocess.run(args, capture_output=True, timeout=120)
    ok = os.path.exists(out)
    print(("OK  " if ok else "FAIL") + " " + png + ("  (%d bytes)" % os.path.getsize(out) if ok else ""))
    if not ok:
        print((r.stderr or b"").decode("utf-8", "ignore")[:400])
    return ok


if not os.path.exists(EDGE):
    print("找不到 Edge：", EDGE)
    sys.exit(1)

fail = 0
for html, png, w, h in PAGES:
    if not shot(html, png, w, h):
        fail += 1
print("\n完成，输出目录：", OUT)
sys.exit(1 if fail else 0)
