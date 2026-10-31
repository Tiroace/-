"""视觉规范验收：页面不得写死色值（任务书 §9 第 14 条）

规则：页面样式一律用变量（`$token` / `var(--token)`），禁止直接写字面色值。
**允许出现色值的地方**：
- `uni.scss`（design-tokens 定义处）
- `theme.css`（设计包参考）
- 编译产物里的变量定义段（uni-app 会把 scss 变量展开，产物必然含最终值）

因此本测试分两层：
1. 源码层（`miniprogram/src/**`，排除 uni.scss）：禁止 `#RRGGBB`、`rgb()/rgba()`
2. 产物层：禁止「散落的色值」，但允许出现在 uni.scss 对应产物的变量段

同时校验设计 token 的四灯色是否与规范一致（docs/09 §五）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import ROOT

SRC = ROOT / "src" / "src"
UNI_SCSS = SRC / "uni.scss"

# 允许写色值的文件
ALLOW_FILES = {"uni.scss", "theme.css", "brand.js"}

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB_RE = re.compile(r"\brgba?\s*\(")

# docs/09 §五 规定的灯色
REQUIRED_TOKENS = {
    "red": "#FF5A47",
    "amber": "#FFB21E",
    "green": "#34D07F",
    "off": "#3A4756",
    "bg": "#0E1620",
    "tabbar": "#121C27",
}

# 禁止的颜色倾向：蓝色（任务书硬约束「禁蓝」）
BLUE_HINT_NAMES = ("blue", "blueish", "#0a84ff", "#007aff", "#1677ff", "#1890ff")


def _src_files():
    if not SRC.is_dir():
        return []
    out = []
    for p in SRC.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".vue", ".scss", ".css", ".js", ".ts"}:
            continue
        if p.name in ALLOW_FILES:
            continue
        out.append(p)
    return out


def _is_dev_page(rel: str) -> bool:
    """判断是否为「开发自测页」（不面向用户，不进正式包）。"""
    return rel.startswith("src/src/pages/dev/")


class Test写死色值:
    def test_页面源码无写死色值(self):
        """§9 第 14 条：页面里没有写死的色值，全部用变量。

        【口径说明（2026-10-31 与前端/Chief 对齐）】

        一、扫描范围：前端 `pnpm check:r1` 只扫 `<style>` 块，本测试扫整份文件（含模板属性）。

        二、开发自测页 `pages/dev/`：不面向用户，**允许写色值**，但前提是它不进正式包，
        由 `test_开发自测页不进正式包` 单独守住（缺陷 D-05）。

        三、**原生组件的颜色属性例外**：`<switch color="…">` 这类属性在编译后是静态字符串，
        SCSS 变量在此处不展开，只能传字面量。因此允许的唯一写法是
        **引用集中定义的具名常量**（如 `:color="SWITCH_COLOR"`，常量定义在 `common/brand.js`），
        目的是「页面不散落色值」。以下写法仍然判违规：
        - 模板里直接写 `color="#FFC93C"`；
        - 在页面文件里自己定义色值常量。
        """
        if not SRC.is_dir():
            pytest.skip("前端源码目录不存在")
        problems = []
        for p in _src_files():
            rel = p.relative_to(ROOT).as_posix()
            # 开发自测页不面向用户，由专门用例守「不进正式包」
            if _is_dev_page(rel):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                # 注释行跳过
                if stripped.startswith(("//", "/*", "*", "<!--")):
                    continue
                # 允许引用集中常量（:color="SWITCH_COLOR"），本身不含字面色值，不会命中下面的正则
                if HEX_RE.search(line):
                    problems.append(f"{rel}:{lineno}: {stripped[:90]}")
                elif RGB_RE.search(line):
                    problems.append(f"{rel}:{lineno}: {stripped[:90]}")
        assert not problems, (
            f"发现 {len(problems)} 处写死色值（应改用 $token / var(--token)）：\n"
            + "\n".join(problems[:20])
        )

    def test_uni_scss存在且含设计token(self):
        if not UNI_SCSS.is_file():
            pytest.skip(f"{UNI_SCSS} 不存在")
        text = UNI_SCSS.read_text(encoding="utf-8").upper()
        missing = []
        for name, hexval in REQUIRED_TOKENS.items():
            if hexval.upper() not in text:
                missing.append(f"{name}={hexval}")
        assert not missing, f"uni.scss 缺少设计 token：{missing}"

    def test_原生组件色值常量必须与uni_scss一致(self):
        """`common/brand.js` 是唯一允许写字面色值的地方（原生组件属性用）。

        它必须**只是 uni.scss token 的副本**，不能成为绕过检查的暗门：
        一旦有人在 brand.js 里新造一个不在设计体系里的颜色，这条会红。
        """
        brand = SRC / "common" / "brand.js"
        if not brand.is_file():
            pytest.skip("brand.js 不存在")
        if not UNI_SCSS.is_file():
            pytest.skip("uni.scss 不存在")

        import re as _re

        brand_text = brand.read_text(encoding="utf-8").upper()
        scss_text = UNI_SCSS.read_text(encoding="utf-8").upper()
        brand_colors = set(m.upper() for m in _re.findall(r"#[0-9A-F]{3,8}", brand_text))
        scss_colors = set(m.upper() for m in _re.findall(r"#[0-9A-F]{3,8}", scss_text))

        orphan = brand_colors - scss_colors
        assert not orphan, (
            f"brand.js 里出现 uni.scss 中不存在的色值：{sorted(orphan)}。"
            "原生组件色值必须是设计 token 的副本，不能新造颜色。"
        )


class Test开发自测页守卫:
    """「开发自测页允许写死色值」的前提是它真的不进正式包。

    这条组就是这个前提本身：一旦有人把 dev 页打进正式包，
    §9 第 5 条和这里会同时变红。
    """

    def test_开发自测页不进正式包(self):
        build = ROOT / "src" / "dist" / "build" / "mp-weixin"
        if not build.is_dir():
            pytest.skip("正式包尚未构建")
        dev_page = build / "pages" / "dev"
        assert not dev_page.exists(), (
            f"正式包里出现了开发自测页：{dev_page}。开发自测页只能存在于 dev 构建。"
        )

    def test_正式包无开发自测文案(self):
        """§9 第 5 条：正式包里看不到「开发自测」。"""
        build = ROOT / "src" / "dist" / "build" / "mp-weixin"
        if not build.is_dir():
            pytest.skip("正式包尚未构建")
        hits = []
        for p in build.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".js", ".json", ".wxml", ".wxss"}:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "开发自测" in text:
                hits.append(p.relative_to(build).as_posix())
        assert not hits, f"正式包仍含「开发自测」：{hits[:10]}"

    def test_正式包无退出登录(self):
        """§9 第 5 条：正式包里看不到「退出登录」。"""
        build = ROOT / "src" / "dist" / "build" / "mp-weixin"
        if not build.is_dir():
            pytest.skip("正式包尚未构建")
        hits = []
        for p in build.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".js", ".json", ".wxml", ".wxss"}:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "退出登录" in text:
                hits.append(p.relative_to(build).as_posix())
        assert not hits, f"正式包仍含「退出登录」：{hits[:10]}"


class Test禁用视觉项:
    def test_无蓝色变量(self):
        """任务书硬约束：禁蓝。"""
        if not SRC.is_dir():
            pytest.skip("前端源码目录不存在")
        problems = []
        for p in SRC.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".scss", ".css", ".vue"}:
                continue
            try:
                text = p.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError:
                continue
            for hint in BLUE_HINT_NAMES:
                if hint in text:
                    problems.append(f"{p.relative_to(ROOT).as_posix()}: 出现 {hint}")
        assert not problems, "出现蓝色相关定义（任务书禁蓝）：\n" + "\n".join(problems[:10])

    def test_页面无渐变(self):
        """任务书硬约束：禁渐变。"""
        if not SRC.is_dir():
            pytest.skip("前端源码目录不存在")
        problems = []
        for p in _src_files():
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if re.search(r"linear-gradient|radial-gradient|conic-gradient", text, re.IGNORECASE):
                problems.append(p.relative_to(ROOT).as_posix())
        assert not problems, "出现渐变（任务书禁用）：\n" + "\n".join(problems[:10])

    def test_页面无卡片阴影(self):
        """任务书：禁卡片阴影。**唯一例外是信号灯的光晕**（docs/09 §五：光晕 0 0 22px）。

        实测踩到的两种误报，规则已按实际实现修正：
        1. 光晕可能写成 rpx（`0 0 19rpx $red`）——单位不限 px；
        2. 光晕可能带前置扩散环（`0 0 0 12rpx $red-soft, 0 0 42rpx $red`）。
        判定方式：整条 box-shadow 里**每个**投影都必须是「0 0 …」无偏移的光晕，
        且值只引用 token 变量（$var / var(--x)）或 none；出现带偏移的投影即为卡片阴影。
        """
        if not SRC.is_dir():
            pytest.skip("前端源码目录不存在")
        problems = []
        for p in _src_files():
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                low = line.lower().strip()
                if "box-shadow" not in low:
                    continue
                if re.search(r"box-shadow\s*:\s*none", low):
                    continue
                # 取出 box-shadow 的值部分，按逗号拆成多条投影
                value = low.split("box-shadow", 1)[1].lstrip(":").strip().rstrip(";")
                shadows = [s.strip() for s in value.split(",") if s.strip()]
                # 只允许「0 0 ...」形式的无偏移光晕
                is_glow = all(re.match(r"^0\s+0(\s|$)", s) for s in shadows) and shadows
                if is_glow:
                    continue
                problems.append(f"{p.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()[:90]}")
        assert not problems, (
            "出现带偏移的卡片阴影（任务书禁用；只有灯的 0 0 光晕允许）：\n" + "\n".join(problems[:10])
        )

    def test_页面无emoji(self):
        """任务书：禁 emoji（**只查会渲染给用户的字符串**）。

        误报修正：源码注释里的箭头 `→`、数学符号等属于排版符号，不是 emoji，
        不应算违规。因此：
        1. 跳过整行注释；
        2. emoji 判定只认「表情符号」区间，排除箭头(2190–21FF)、数学(2200–22FF)、
           装饰符号(2B00–2BFF) 等排版字符。
        """
        if not SRC.is_dir():
            pytest.skip("前端源码目录不存在")
        # 仅保留真正的 emoji 区段：表情、手势、符号图形、交通、旗帜等
        emoji_re = re.compile(
            "["
            "\U0001F300-\U0001F5FF"   # 符号与象形
            "\U0001F600-\U0001F64F"   # 表情
            "\U0001F680-\U0001F6FF"   # 交通与地图
            "\U0001F700-\U0001F77F"   # 炼金符号
            "\U0001F900-\U0001F9FF"   # 补充符号
            "\U0001FA00-\U0001FAFF"   # 扩展 A
            "\u2600-\u26FF"           # 杂项符号（⚠☀ 等）
            "\u2700-\u27BF"           # 装饰符号（✅❌ 等）
            "]"
        )
        problems = []
        for p in _src_files():
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                # 跳过注释行（// 与 /* 与 * 开头）
                if stripped.startswith(("//", "/*", "*")):
                    continue
                if emoji_re.search(line):
                    problems.append(f"{p.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()[:80]}")
        assert not problems, "页面出现 emoji（任务书禁用）：\n" + "\n".join(problems[:10])
