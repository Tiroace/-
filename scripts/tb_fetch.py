"""通过 Tabbit CLI 抓取指定 URL 的正文，保存为 UTF-8 JSON。

用法：python scripts/tb_fetch.py <task> <request-id> <url1> <url2> ...

输出：var/fetched/<request-id>.json（列表，每项 {url,status,text}）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "var" / "fetched"
CLI = Path(os.environ.get("LOCALAPPDATA", "")) / "Tabbit" / "LocalAgent" / "bin" / "tabbit-cli.exe"

JS_TEMPLATE = """
const targets = __URLS__;
const out = [];
for (const url of targets) {
  try {
    const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(1500);
    const text = await page.evaluate(() => {
      const ps = Array.from(document.querySelectorAll("p"));
      const joined = ps.map((x) => x.innerText.trim()).filter((t) => t.length > 20).join("\\n");
      if (joined.length > 300) return joined.slice(0, 8000);
      return (document.body.innerText || "").replace(/\\n{2,}/g, "\\n").slice(0, 8000);
    });
    out.push({ url: page.url(), status: resp ? resp.status() : -1, text: text });
  } catch (e) {
    out.push({ url, error: String(e.message).slice(0, 120) });
  }
}
return out;
"""


def fetch(task: str, req_id: str, urls: list[str]) -> list[dict]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    js = JS_TEMPLATE.replace("__URLS__", json.dumps(urls, ensure_ascii=False))
    js_path = OUT_DIR / f"{req_id}.js"
    js_path.write_text(js, encoding="utf-8")

    res_path = OUT_DIR / f"{req_id}.raw.json"
    cmd = f'"{CLI}" nodejs --task {task} --request-id {req_id} --timeout-ms 170000 < "{js_path}"'
    with res_path.open("wb") as fh:
        subprocess.run(cmd, shell=True, stdout=fh, stderr=subprocess.DEVNULL)

    raw = res_path.read_bytes()
    text = None
    for enc in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError("无法解码 CLI 输出")

    payload = json.loads(text)
    result = payload.get("result", {})
    if "resourceId" in result:
        # 结果过大，转存资源
        rp = OUT_DIR / f"{req_id}.res.json"
        cmd = f'"{CLI}" resource --task {task} --resource {result["resourceId"]} --offset 0 --max-bytes 65536'
        with rp.open("wb") as fh:
            subprocess.run(cmd, shell=True, stdout=fh, stderr=subprocess.DEVNULL)
        rraw = rp.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "utf-8"):
            try:
                rdata = json.loads(rraw.decode(enc))
                break
            except Exception:
                rdata = None
        if rdata and "data" in rdata:
            return json.loads(rdata["data"])

    return result.get("value", [])


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    task, req_id = sys.argv[1], sys.argv[2]
    urls = sys.argv[3:]
    items = fetch(task, req_id, urls)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{req_id}.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    for it in items:
        if "error" in it:
            print(f"ERR {it['url'][:60]}: {it['error']}")
        else:
            print(f"OK  {it.get('status')} len={len(it.get('text',''))} {it['url'][:70]}")
    print(f"\n已保存：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
