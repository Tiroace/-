// 规则版（rules 引擎）用的 judge.js 空实现。
//
// 为什么要有这个文件：双版本令第三节要求「DeepSeek 相关代码用动态引入或条件编译，
// 保证规则版打包后不包含」。uni-app 对自定义条件编译宏（#ifdef QBL_XXX）没有注册入口，
// 未注册的宏会把整段代码**静默删掉**——那会把逻辑一起删没，比多打包几十 KB 危险得多。
// 所以改用构建期替换：vite.config.js 在引擎为 rules 时把 '@/services/judge.js'
// 别名指到本文件。规则版包里因此只剩这些空函数，不含提示词、接口地址、模型名。
// DeepSeek 版（VITE_ENGINE=deepseek）仍然用真的 judge.js。

export function isVisionJudgeAvailable() {
  return false;
}

export async function toBase64() {
  return null;
}

export function judgeImages() {
  return Promise.reject(new Error('RULE_ENGINE'));
}

export function validateHits() {
  return [];
}
