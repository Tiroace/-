// 注册 `@/` 别名解析后再跑 selfcheck.mjs。
// 用法：node --import ./tests/register-alias.mjs tests/selfcheck.mjs
import { register } from 'node:module';
import { pathToFileURL } from 'node:url';

register('./alias-loader.mjs', pathToFileURL('D:/qiuzhibilei/src/tests/'));
