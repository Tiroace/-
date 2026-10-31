// 通用格式化工具：脱敏、时间、字数控制。
// 脱敏用于分享卡片和展示层（下派书 §8：分享卡片自动打码公司名、HR 姓名、电话、微信号）。

// 手机号：138****1234
export function maskPhone(text) {
  if (!text) return text;
  return String(text).replace(/1[3-9]\d{9}/g, (m) => m.slice(0, 3) + '****' + m.slice(7));
}

// 微信号/QQ 号这类纯数字长串：只保留首尾
export function maskIdLike(text) {
  if (!text) return text;
  return String(text).replace(/\b\d{6,12}\b/g, (m) => m.slice(0, 2) + '****' + m.slice(-2));
}

// 公司名：保留首字与「有限公司/公司/集团」后缀，中间打码
// 例：某某网络科技有限公司 -> 某*网络*技有限公司（保留可读性，隐藏可检索的完整名）
export function maskCompanyName(name) {
  if (!name) return '一家招聘企业';
  const s = String(name);
  if (s.length <= 2) return s[0] + '*';
  if (s.length <= 4) return s[0] + '**' + s[s.length - 1];
  return s.slice(0, 1) + '***' + s.slice(-2);
}

// HR 姓名：张* 、 李**
export function maskPersonName(name) {
  if (!name) return '某招聘方';
  const s = String(name);
  if (s.length === 1) return s + '*';
  return s[0] + '*'.repeat(Math.min(s.length - 1, 2));
}

// 一次脱敏全部敏感信息（分享卡片/对外展示用）
export function maskAll(text) {
  if (!text) return '';
  let out = String(text);
  out = maskPhone(out);
  out = out.replace(/[a-zA-Z][-_a-zA-Z0-9]{5,19}/g, (m) => (m.length >= 8 ? m.slice(0, 2) + '****' : m));
  out = maskIdLike(out);
  return out;
}

// 将毫秒格式化为「12 秒」「1 分 05 秒」
export function formatDuration(ms) {
  const total = Math.max(0, Math.floor((ms || 0) / 1000));
  if (total < 60) return total + ' 秒';
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m + ' 分 ' + (s < 10 ? '0' + s : s) + ' 秒';
}

// 时间戳 → MM-DD HH:mm
export function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(Number(ts));
  const p = (n) => (n < 10 ? '0' + n : '' + n);
  return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

// 取前 N 个字，超出加省略号
export function clip(text, n = 30) {
  const s = String(text || '');
  return s.length > n ? s.slice(0, n) + '…' : s;
}
