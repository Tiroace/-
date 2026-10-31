// 微信开发者工具自动化：用 automator.launch() 自己拉起自动化端口
// 用法：node launch-smoke.js [projectPath]
const automator = require('miniprogram-automator');

const PROJECT = process.argv[2] || 'D:\\qiuzhibilei\\src\\dist\\build\\mp-weixin';
const CLI = 'D:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat';

(async () => {
  let miniProgram;
  try {
    miniProgram = await automator.launch({
      cliPath: CLI,
      projectPath: PROJECT,
      port: 9420,
      timeout: 90000,
    });
    console.log('LAUNCH OK');
    const page = await miniProgram.currentPage();
    console.log('route =', page.path);
    await miniProgram.disconnect();
    console.log('DONE');
  } catch (e) {
    console.log('LAUNCH FAILED:', e && e.message);
    if (e && e.stack) console.log(e.stack.split('\n').slice(0, 4).join('\n'));
    process.exitCode = 1;
  }
})();
