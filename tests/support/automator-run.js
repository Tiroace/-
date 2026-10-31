// 微信开发者工具自动化连接脚本
//
// 背景（详见 reports/E1 §11）：
//   - miniprogram-automator 0.13 的 connect() 要求 IDE 该窗口已用「自动化端口」打开；
//     而 `cli.bat auto --port 9420` 里的 9420 是 **IDE HTTP 端口**，不是自动化 WS 端口。
//   - launch() 会自己带 `--auto-port <p>` 拉起独立自动化端口，是正路。
//   - launch() 内部用 child_process.spawn 直接执行 cliPath，路径带空格/中文时会失败，
//     故给 cliPath 一个不带空格的短路径（8.3 名）或用 cwd 规避。
//
// 用法：node automator-run.js [projectPath] [port]
const automator = require('miniprogram-automator');
const fs = require('fs');

const PROJECT = process.argv[2] || 'D:\\qiuzhibilei\\src\\dist\\build\\mp-weixin';
const PORT = Number(process.argv[3] || 9420);

// 安装目录的 8.3 短路径（用 gci 的 -Force 拿不到，直接试常见形式）
function findCli() {
  const candidates = [
    'D:\\PROGRA~1\\Tencent\\微信WE~1\\cli.bat',
    'D:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat',
  ];
  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return c;
    } catch (_) {}
  }
  return candidates[1];
}

(async () => {
  const cliPath = findCli();
  console.log('cliPath =', cliPath);
  console.log('project =', PROJECT);
  let miniProgram;
  try {
    miniProgram = await automator.launch({
      cliPath,
      projectPath: PROJECT,
      port: PORT,
      timeout: 120000,
      cwd: 'D:\\Program Files (x86)\\Tencent\\微信web开发者工具',
    });
    console.log('LAUNCH OK');
    const page = await miniProgram.currentPage();
    console.log('ROUTE =', page.path);
    await miniProgram.disconnect();
    console.log('DONE');
  } catch (e) {
    console.log('LAUNCH FAILED:', e && e.message);
    process.exitCode = 1;
  }
})();
