/**
 * IDE 自动化通道自检：确认 automator 能连上 9422 并读到页面。
 *
 * 为什么需要这个：2026-11-03 起 IDE 自动化归软件测试者负责，接手第一件事
 * 是能证明「通道是通的」，而不是等截图脚本跑挂了才发现。本脚本只读不写，
 * 不截图、不点击，跑完立刻断开，不会打断老板扫码。
 *
 * 用法：node tests/ide-probe.mjs [--json]
 *   先确保 IDE 已 `cli.bat auto ... --auto-port 9422`（端口 9422 在监听）
 */
import automator from "miniprogram-automator";
import { existsSync } from "node:fs";
import { join } from "node:path";

const REPO = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
// 优先新目录 src，回退旧目录 miniprogram（仓库重组过渡期）
const CANDIDATES = [
  join(REPO, "src", "dist", "build", "mp-weixin"),
  join(REPO, "miniprogram", "dist", "build", "mp-weixin"),
];
const PROJECT = CANDIDATES.find((p) => existsSync(p));

const AUTO_PORT = Number(process.env.QBL_AUTO_PORT || 9422);

function fail(msg) {
  console.error(`✗ ${msg}`);
  process.exit(1);
}

if (!PROJECT) {
  fail(`找不到小程序构建产物，检查过：\n  ${CANDIDATES.join("\n  ")}\n先跑构建：cd src && pnpm build:mp-weixin`);
}

let mini;
try {
  mini = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${AUTO_PORT}` });
} catch (err) {
  fail(
    `连不上 automator（${AUTO_PORT}）：${err.message}\n` +
      `  排查：1) 9422 是否监听  2) 是否先跑过 cli.bat auto ... --auto-port 9422`,
  );
}

try {
  const page = await mini.currentPage();
  if (!page) fail("连上了但拿不到当前页面");

  const path = page.path;
  // 用 $$('view') 读渲染层文本——前端实测过 page.data()/$vm.$el 都不可靠
  const nodes = await page.$$("view");
  const texts = [];
  for (const n of nodes) {
    try {
      const t = (await n.text()) || "";
      if (t.trim()) texts.push(t.trim());
    } catch {
      /* 单个节点读失败不影响整体 */
    }
  }
  const joined = texts.join(" ");

  const result = {
    ok: true,
    project: PROJECT,
    autoPort: AUTO_PORT,
    pagePath: path,
    viewNodes: nodes.length,
    textNodes: texts.length,
    textChars: joined.length,
    sample: joined.slice(0, 120),
  };

  if (process.argv.includes("--json")) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log("✓ IDE 自动化通道正常");
    console.log(`  工程：${PROJECT}`);
    console.log(`  端口：${AUTO_PORT}`);
    console.log(`  当前页：${path}`);
    console.log(`  渲染节点：view ${nodes.length} 个，有文本 ${texts.length} 个，共 ${joined.length} 字`);
    console.log(`  文本样本：${result.sample}`);
  }

  // 能读到文本才算真的通——空文本说明通道半死，必须报错而不是打印通过
  if (joined.length === 0) {
    fail("连上了但读不到任何渲染文本，通道不可用");
  }
} finally {
  try {
    await mini.disconnect();
  } catch {
    /* ignore */
  }
}
