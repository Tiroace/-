"""云上真实图识别验收（走公网接口，拿到 trace.ocr.source 与耗时）。

用途：老板要的 ③④ —— `trace.ocr.source == rapidocr` + 单张/3 张耗时。
前提：控制台已开启「允许公网访问」，且拿到服务默认域名。

用法：
    python ops/scripts/verify_cloud_ocr.py --url https://xxx.run.tcloudbase.com
    python ops/scripts/verify_cloud_ocr.py --url ... --n 1 --triples 1   # 快速模式

流程：/auth/login 拿 token → /analysis/upload 传图 → /analysis 建任务 → 轮询 /analysis/{id}
注意：生产环境 QBL_DEV_MODE=0 时 mock 登录会被拒；若登录失败脚本会明确提示，
      此时改用「云端调试」里跑或在容器内跑 eval/eval_api_e2e.py。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAW_DIR = Path(r"D:\qiuzhibilei-local-private\raw-baseline")
OUT = Path(r"D:\qiuzhibilei\ops\evidence\cloud-ocr-verify.txt")


def req(method: str, url: str, data: bytes | None = None,
        headers: dict | None = None, timeout: int = 60) -> tuple[int, bytes]:
    r = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def multipart(field: str, filename: str, content: bytes, ct: str = "image/png") -> tuple[bytes, str]:
    boundary = "----qbl" + uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {ct}\r\n\r\n".encode(),
        content, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/form-data; boundary={boundary}"


def login(base: str) -> str | None:
    body = json.dumps({"platform": "toutiao", "code": f"verify-{int(time.time())}"}).encode()
    st, resp = req("POST", f"{base}/auth/login", body, {"Content-Type": "application/json"})
    if st != 200:
        print(f"  登录失败 HTTP {st}: {resp[:200].decode('utf-8', 'replace')}")
        return None
    try:
        return json.loads(resp)["data"]["token"]
    except Exception:  # noqa: BLE001
        return None


def analyze_once(base: str, token: str, paths: list[Path]) -> dict:
    hdr = {"Authorization": f"Bearer {token}"}
    ids = []
    for p in paths:
        body, ct = multipart("image", p.name, p.read_bytes())
        st, resp = req("POST", f"{base}/analysis/upload", body, {**hdr, "Content-Type": ct})
        if st != 200:
            return {"error": f"上传 {p.name} 失败 HTTP {st}: {resp[:150].decode('utf-8','replace')}"}
        ids.append(json.loads(resp)["data"]["image_id"])

    t0 = time.perf_counter()
    body = json.dumps({"image_ids": ids}).encode()
    st, resp = req("POST", f"{base}/analysis", body, {**hdr, "Content-Type": "application/json"})
    if st != 200:
        return {"error": f"建任务失败 HTTP {st}: {resp[:200].decode('utf-8','replace')}"}
    task_id = json.loads(resp)["data"]["task_id"]

    for _ in range(180):
        time.sleep(1)
        st, resp = req("GET", f"{base}/analysis/{task_id}", None, hdr)
        if st != 200:
            return {"error": f"查任务 HTTP {st}"}
        d = json.loads(resp)["data"]
        if d.get("status") in ("done", "failed"):
            elapsed = time.perf_counter() - t0
            return {"elapsed": elapsed, "data": d}
    return {"error": "轮询超时"}


def find_source(d: dict) -> str | None:
    """从报告里挖 trace.ocr.source，兼容几种层级。"""
    for path in (("trace", "ocr", "source"), ("report", "trace", "ocr", "source")):
        cur = d
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and isinstance(cur, str):
            return cur
    # 兜底：递归找
    def walk(o):
        if isinstance(o, dict):
            if "ocr" in o and isinstance(o["ocr"], dict) and "source" in o["ocr"]:
                return o["ocr"]["source"]
            for v in o.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None
    return walk(d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--n", type=int, default=3, help="单张测试张数")
    ap.add_argument("--triples", type=int, default=2, help="三张组合组数")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        lines.append(s)

    say("=" * 66)
    say("云上 OCR 验收（③④）")
    say("=" * 66)
    say(f"地址: {base}")

    imgs = sorted(RAW_DIR.glob("*.png"))
    if not imgs:
        say(f"❌ 本地没有真实图：{RAW_DIR}")
        return 1
    say(f"本地真实图: {len(imgs)} 张")
    say("")

    token = login(base)
    if not token:
        say("❌ 拿不到 token，无法继续。")
        say("   生产环境 QBL_DEV_MODE=0 时 mock 登录会被拒——")
        say("   改走「云端调试」里跑 eval/eval_api_e2e.py，或临时开 DEV_MODE 验证后再关。")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        return 1
    say("✅ 登录成功")
    say("")

    # 单张
    single: list[float] = []
    sources: list[str] = []
    say("-" * 66)
    say("【③④-a】单张")
    say("-" * 66)
    for p in imgs[: args.n]:
        r = analyze_once(base, token, [p])
        if "error" in r:
            say(f"{p.stem:<12} ❌ {r['error']}")
            continue
        src = find_source(r["data"])
        sources.append(src or "未找到")
        single.append(r["elapsed"])
        say(f"{p.stem:<12} {r['elapsed']:6.2f}s  ocr.source={src}")

    # 三张
    triples: list[float] = []
    say("")
    say("-" * 66)
    say("【③④-b】三张")
    say("-" * 66)
    for i in range(args.triples):
        batch = imgs[i * 3: i * 3 + 3]
        if len(batch) < 3:
            break
        r = analyze_once(base, token, batch)
        if "error" in r:
            say(f"组{i+1} ❌ {r['error']}")
            continue
        src = find_source(r["data"])
        sources.append(src or "未找到")
        triples.append(r["elapsed"])
        say(f"组{i+1:<4} {r['elapsed']:6.2f}s  ocr.source={src}  images={r['data'].get('ocr_images')}")

    # 判定
    say("")
    say("=" * 66)
    ok_src = bool(sources) and all(s == "rapidocr" for s in sources)
    say(f"ocr.source 全部为 rapidocr: {'✅' if ok_src else '❌'}  实测值 {set(sources) or '无'}")
    ok = ok_src
    if single:
        p95 = max(single)
        say(f"单张 P95≈{p95:.2f}s  线 ≤10s  {'✅' if p95 <= 10 else '❌'}")
        ok &= p95 <= 10
    if triples:
        p95 = max(triples)
        say(f"3 张 P95≈{p95:.2f}s  线 ≤25s  {'✅' if p95 <= 25 else '❌'}")
        ok &= p95 <= 25
    say(f"总判定：{'✅ 通过' if ok else '❌ 未通过'}")
    say("=" * 66)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[验收] 已存：{OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
