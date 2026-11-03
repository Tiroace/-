// 检查记录（老板 2026-11-04 定）：每次查完把报告 JSON、时间、红黄绿、套路标题存进手机本地
//
// 规则：
// - 保留 7 天、最多 50 条；
// - **不存截图**（只存文字与结论）；
// - 「我的」页列表从这里取，点开能重看；
// - 「查过的工作」「亮过的红灯」两个数也从这里算。
//
// 全部用 uni.getStorageSync / setStorageSync，不依赖网络。

const KEY = 'qbl_history_v1';
const KEEP_DAYS = 7;
const KEEP_MAX = 50;

function nowMs() {
  return Date.now();
}

function readAll() {
  try {
    const raw = uni.getStorageSync(KEY);
    if (!raw) return [];
    const list = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return Array.isArray(list) ? list : [];
  } catch (e) {
    return [];
  }
}

function writeAll(list) {
  try {
    uni.setStorageSync(KEY, JSON.stringify(list));
  } catch (e) {
    /* 存储满了也不该影响用户看报告 */
  }
}

// 过期清理：超过 7 天或超过 50 条，旧的先丢
export function pruneHistory(list) {
  const cutoff = nowMs() - KEEP_DAYS * 24 * 3600 * 1000;
  return list
    .filter((it) => it && it.at && it.at >= cutoff)
    .sort((a, b) => b.at - a.at)
    .slice(0, KEEP_MAX);
}

// 存一条。report 是报告对象，meta 可带 scheme 标题与套路编号
export function saveHistory(report, { schemeTitle = '', schemeId = '', patterns = [] } = {}) {
  if (!report || !report.overall) return null;
  const item = {
    id: 'h_' + nowMs().toString(36) + '_' + Math.random().toString(36).slice(2, 6),
    at: nowMs(),
    overall: report.overall,
    summary: report.summary || '',
    scheme_title: schemeTitle || '',
    scheme_id: schemeId || '',
    patterns: Array.isArray(patterns) ? patterns.slice(0, 12) : [],
    // 只存报告本体，不存截图、不存 ocr 原文里的手机号等（报告本身已脱敏）
    report,
  };
  const list = pruneHistory([item].concat(readAll()));
  writeAll(list);
  return item;
}

export function listHistory() {
  const list = pruneHistory(readAll());
  writeAll(list); // 顺手把清理后的写回，避免越积越多
  return list;
}

export function getHistory(id) {
  return listHistory().find((it) => it.id === id) || null;
}

// 「我的」页两个数：查过的工作（所有记录）、亮过的红灯（overall=red 的记录）
export function historyStats() {
  const list = listHistory();
  return {
    checked: list.length,
    red: list.filter((it) => it.overall === 'red').length,
  };
}

export function clearHistory() {
  writeAll([]);
}
