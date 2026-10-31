// 给 Node 直接跑源码时提供 `@/` 别名解析（等价于 vite.config.js 里 uni-app 默认的 @ → src）。
// 仅供 tests/ 下的自测脚本使用，不参与小程序构建。
import { pathToFileURL } from 'node:url';

const SRC = pathToFileURL('D:/qiuzhibilei/src/src/').href;

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith('@/')) {
    return nextResolve(SRC + specifier.slice(2), context);
  }
  return nextResolve(specifier, context);
}
