"""A7-4 反向验证：临时注入越权缺陷，确认用例能抓到。

用法：python scripts/verify_a7_4.py inject|restore
"""
import sys
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "backend" / "app" / "routers" / "analysis.py"
BAK = P.with_suffix(".py.a74bak")

GOOD = 'if task is None or task["user_id"] != user["id"]:'
BAD = "if task is None:"


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    src = P.read_text(encoding="utf-8")
    if action == "inject":
        if GOOD not in src:
            print("没找到原始越权判断，代码可能已改，请人工确认")
            return 2
        BAK.write_text(src, encoding="utf-8")
        P.write_text(src.replace(GOOD, BAD), encoding="utf-8")
        print("已注入越权缺陷（去掉 user_id 比对）")
        return 0
    if action == "restore":
        if not BAK.is_file():
            print("没有备份可恢复")
            return 2
        P.write_text(BAK.read_text(encoding="utf-8"), encoding="utf-8")
        BAK.unlink()
        print("已恢复")
        return 0
    print("用法：python scripts/verify_a7_4.py inject|restore")
    return 1


if __name__ == "__main__":
    sys.exit(main())
