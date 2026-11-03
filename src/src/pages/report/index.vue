<template>
  <view class="page">
    <!-- ① 顶部标识 -->
    <view class="top-banner">
      <text class="chip">系统自动生成 · 仅供参考</text>
      <text v-if="isSample" class="chip chip-sample">示例报告 · 内容是虚构的，不指向任何公司</text>
    <!-- 本机判断路径标识：只用于核对跑的是哪条链路，不出现任何模型名 -->
    <text v-if="isLocalReport" class="chip chip-sample">本机判断 · {{ localTag }}</text>
    </view>

    <view class="main">
      <!-- ② 结论区：三种灯 + 标题 + 副标题 -->
      <view class="verdict" :class="'verdict-' + overall">
        <view class="pole">
          <view class="pole-lamp" :class="{ on: overall === 'red' }"></view>
          <view class="pole-lamp" :class="{ on: overall === 'amber' }"></view>
          <view class="pole-lamp" :class="{ on: overall === 'green' }"></view>
        </view>
        <view class="verdict-text">
          <text class="verdict-title">{{ verdictTitle }}</text>
          <text class="verdict-sub">{{ verdictSub }}</text>
        </view>
      </view>

      <!-- ③ 依据行 -->
      <text class="basis">依据你上传的截图，{{ checkTime }} 检查</text>

      <!-- ④ 6 项检查：2 列网格，顺序固定 -->
      <text class="h2">6 项检查</text>
      <view class="dims">
        <view v-for="d in dimensions" :key="d.key" class="dim">
          <view class="dim-head">
            <SignalLamp :level="d.level === 'none' ? 'off' : d.level" size="sm" />
            <text class="dim-name">{{ d.name }}</text>
          </view>
          <text class="dim-short" :class="{ 'dim-none': d.level === 'none' }">{{ dimShort(d) }}</text>
        </view>
      </view>

      <!-- ⑤ 具体发现 -->
      <view class="h2row">
        <text class="h2">具体发现</text>
        <text class="h2-side" v-if="findings.length">按风险从高到低</text>
      </view>

      <view v-if="!findings.length" class="card empty-findings">
        <text class="empty-t">{{ emptyFindingsText }}</text>
      </view>

      <view v-for="(f, idx) in findings" :key="idx" class="card finding">
        <view class="finding-head">
          <SignalLamp :level="f.level" size="sm" />
          <text class="finding-title">{{ f.title }}</text>
          <text class="source-tag" :class="'src-' + f.source">{{ sourceLabel(f.source) }}</text>
        </view>
        <view class="quote" :class="'quote-' + f.level">
          <text class="quote-text">「{{ contextBefore(f) }}</text>
          <text class="quote-mark" :class="'mark-' + f.level">{{ f.evidence }}</text>
          <text class="quote-text">{{ contextAfter(f) }}」</text>
        </view>
        <text class="reason">{{ f.reason }}</text>
      </view>

      <!-- ⑥ 面试前问 HR -->
      <text class="h2">{{ questionTitle }}</text>
      <view class="card qlist">
        <view v-for="(q, idx) in shownQuestions" :key="idx" class="q-item">
          <view class="q-index"><text class="q-num">{{ idx + 1 }}</text></view>
          <text class="q-text">{{ q }}</text>
        </view>
        <view class="btn-copy" @tap="copyQuestions"><text>复制</text></view>
      </view>

      <!-- ⑦ 自己也能核实 -->
      <text class="h2">自己也能核实</text>
      <view class="card vlist">
        <view v-for="(v, idx) in report.how_to_verify" :key="idx" class="v-item">
          <view class="v-dot"></view>
          <text class="v-text">{{ v }}</text>
        </view>
      </view>

      <!-- ⑦b 公司核实卡片：从截图文字里提取公司全称，一键复制 + 引导去官方渠道自查
           不接第三方数据，只提供复制和跳转指引
           两态（06 号 §三 #11）：有全称 → 复制全称 + 两个官网；无全称 → 复制一句问 HR 的话 -->
      <view v-if="companyName" class="card corp-card">
        <view class="corp-head">
          <text class="corp-title">查一下这家公司</text>
          <text class="corp-tag">来自截图</text>
        </view>
        <view class="corp-name-row">
          <text class="corp-name">{{ companyName }}</text>
        </view>
        <view class="corp-copy" @tap="copyCompany">
          <text>复制公司全称</text>
        </view>
        <text class="corp-tip">复制后去下面两个网站搜一下，核对是否真实存在、有没有人反映过问题。</text>
        <view class="corp-links">
          <view class="corp-link" @tap="openVerifySite('gsxt')">
            <text class="corp-link-t">国家企业信用信息公示系统</text>
            <text class="corp-link-s">查工商登记、经营范围、经营状态</text>
          </view>
          <view class="corp-link corp-link-last" @tap="openVerifySite('heimao')">
            <text class="corp-link-t">黑猫投诉</text>
            <text class="corp-link-s">查有没有人反映过收费、欠薪等问题</text>
          </view>
        </view>
      </view>
      <view v-else class="card corp-card">
        <view class="corp-head">
          <text class="corp-title">查一下这家公司</text>
        </view>
        <text class="corp-tip">{{ ASK_HR_SUB }}</text>
        <view class="corp-copy" @tap="copyAskHr">
          <text>{{ askHrCopied ? '已复制' : '复制这句话问 HR' }}</text>
        </view>
      </view>
      <!-- ⑧ 已经交了钱？只在 overall=red 时出现 -->
      <view v-if="overall === 'red'" class="card money-card">
        <text class="money-title">已经交了钱？</text>
        <text class="money-body">先停止转账，保存好聊天记录和转账截图，然后报警。</text>
        <view class="money-btns">
          <view class="btn-line" @tap="callPhone('110')"><text>拨打 110</text></view>
          <view class="btn-line btn-line-gap" @tap="callPhone('96110')"><text>反诈专线 96110</text></view>
        </view>
        <!-- 12333 不做拨号键（D21）：避免用户误以为打 12333 能追回被骗的钱。
             它是劳动权益咨询热线，只做文字提示，放在两个拨号按钮下方。 -->
        <view class="labour-tip">
          <text class="labour-tip-text">劳动权益问题（欠薪、不缴社保、扣押证件），可拨 12333</text>
        </view>
        <view class="help-lines">
          <view v-for="(tip, idx) in helpTips" :key="idx" class="help-line">
            <view class="help-dot"></view>
            <text class="help-text">{{ tip }}</text>
          </view>
        </view>
      </view>

      <!-- ⑨ 免责声明 + 判断不准 -->
      <view class="disclaimer-box">
        <text class="disclaimer">{{ disclaimer }}</text>
        <!-- 路线调整令：一期不用大模型，不展示模型名和备案号，只标规则版本 -->
        <text class="model-line">规则版本：{{ report.rules_version || '—' }} ｜ 套路库版本：{{ report.pattern_db_version || '—' }}</text>
        <view class="inaccurate" @tap="gotoFeedback"><text>判断不准？告诉我们</text></view>
      </view>
    </view>

    <!-- ⑩ 底部按钮 -->
    <view class="bottom-bar">
      <view class="btn-share" @tap="onShare"><text>提醒朋友</text></view>
      <view class="btn-primary" @tap="gotoIndex"><text>再查一份</text></view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import SignalLamp from '@/components/SignalLamp.vue';
import { fetchAnalysis } from '@/services/api.js';
import { getExampleReport } from '@/common/exampleReports.js';
import { DIMENSIONS, SOURCE_LABEL, SHARE_TITLE } from '@/common/brand.js';
// 免责声明（D20 定稿）+ 高危求助提示（110 / 96110 / 12333），统一来自 constants.js
import { HELP_TIPS, DISCLAIMER_TEXT } from '@/common/constants.js';

defineOptions({
  name: 'ReportPage',
  onShareAppMessage() {
    // 分享标题不带任何公司名（合规 §8）
    return { title: SHARE_TITLE, path: '/pages/index/index' };
  },
});

// 免责声明统一从 constants.js 引用（D20 定稿，全产品唯一版本，不要在本页再写一份）
// 高危求助提示（§8：110 报警 / 96110 反诈 / 12333 劳动权益）
const helpTips = HELP_TIPS;

// 4 种 overall 的固定标题（一字不改，D16：green 用「截图里没看到明显风险」）
const VERDICT_TITLE = {
  red: '这份工作，建议先别去',
  amber: '先问清楚，再决定去不去',
  green: '截图里没看到明显风险',
  unknown: '截图信息不够，再补一张',
};

const report = ref(emptyReport());
const isSample = ref(false);
// 本地识图报告（截图在手机上直接判断，不经过服务器）
const isLocalReport = ref(false);
// 路径标识：便于核对线上跑的是本机判断还是服务器判断（不出现模型名）
const localTag = computed(() => {
  const r = report.value || {};
  return r.rules_version ? r.rules_version : '';
});
const disclaimer = DISCLAIMER_TEXT;
const checkTime = ref('');

function emptyReport() {
  return {
    is_job_posting: true,
    overall: 'unknown',
    summary: '',
    dimensions: [],
    findings: [],
    questions_to_ask: [],
    how_to_verify: [],
    // 一期不用大模型：版本字段叫 rules_version（引擎契约已改）
    // 留空而不是写死版本号，真实版本由引擎/后端返回，展示时不冒充某个版本
    rules_version: '',
    pattern_db_version: '',
  };
}

const overall = computed(() => {
  const o = report.value.overall;
  return ['red', 'amber', 'green'].includes(o) ? o : 'unknown';
});

const verdictTitle = computed(() => VERDICT_TITLE[overall.value]);

// 副标题统计：只数红黄绿，灰灯不计；0 项省略；unknown 换固定文案
const verdictSub = computed(() => {
  if (overall.value === 'unknown') {
    return '截图里没读到岗位、薪资、公司这些关键信息';
  }
  const dims = report.value.dimensions || [];
  const count = (lv) => dims.filter((d) => d.level === lv).length;
  const parts = [];
  const r = count('red');
  const a = count('amber');
  const g = count('green');
  if (r) parts.push(r + ' 项红灯');
  if (a) parts.push(a + ' 项黄灯');
  if (g) parts.push(g + ' 项绿灯');
  return parts.length ? parts.join('，') : '';
});

// 6 维：按固定顺序排，缺的补成灰灯（后端应保证齐全，前端兜底不崩）
const dimensions = computed(() => {
  const byKey = {};
  (report.value.dimensions || []).forEach((d) => {
    byKey[d.key] = d;
  });
  return DIMENSIONS.map((dim) => {
    const got = byKey[dim.key];
    return {
      key: dim.key,
      name: dim.name,
      level: got ? got.level : 'none',
      short: got ? got.short : '',
    };
  });
});

// 灰灯固定文案「截图里没提到」，不许写「正常/无风险」
function dimShort(d) {
  if (d.level === 'none') return '截图里没提到';
  return d.short || '';
}

// findings 排序：红 → 黄 → 绿，同色按 6 维顺序
const FINDING_ORDER = { red: 0, amber: 1, green: 2 };
const DIM_ORDER = { fee: 0, work: 1, title: 2, pay: 3, company: 4, contract: 5 };

const findings = computed(() => {
  const list = (report.value.findings || []).slice();
  // 证据可追溯的底线：evidence 不在 context 里就不上屏（§4.3）
  const valid = list.filter((f) => {
    if (!f.evidence || !f.context) return false;
    return String(f.context).includes(String(f.evidence));
  });
  valid.sort((a, b) => {
    const la = FINDING_ORDER[a.level] ?? 9;
    const lb = FINDING_ORDER[b.level] ?? 9;
    if (la !== lb) return la - lb;
    const da = DIM_ORDER[a.dimension] ?? 9;
    const db = DIM_ORDER[b.dimension] ?? 9;
    return da - db;
  });
  return valid;
});

const emptyFindingsText = computed(() =>
  overall.value === 'unknown' ? '截图里没读到能判断的内容' : '这张截图里没发现具体问题'
);

// 公司全称：从截图原文（evidence/context）里提取，不调外部数据
// 识别特征：以「有限公司 / 有限责任公司 / 股份公司 / 集团 / 分公司」等结尾的中文名
const COMPANY_RE =
  /[\u4e00-\u9fa5（）()]{2,30}?(?:有限责任公司|股份有限公司|有限公司|分公司|集团|工作室|个体工商户)/;

const companyName = computed(() => {
  const texts = [];
  if (report.value.company) texts.push(report.value.company);
  (report.value.findings || []).forEach((f) => {
    if (f.context) texts.push(f.context);
    if (f.evidence) texts.push(f.evidence);
  });
  // 也扫一下核实方法，有时会带公司名
  (report.value.how_to_verify || []).forEach((t) => texts.push(t));
  for (const t of texts) {
    const m = String(t).match(COMPANY_RE);
    if (m) {
      // 去掉开头可能粘上的动词/标点
      const name = m[0].replace(/^(公司全称[:：]?|名称[:：]?|去|到|在)/, '').trim();
      if (name.length >= 4) return name;
    }
  }
  return '';
});

// 查企业信息的官方站点（只做跳转引导，不接第三方数据）
const VERIFY_SITES = {
  gsxt: { name: '国家企业信用信息公示系统', url: 'https://www.gsxt.gov.cn/index.html' },
  heimao: { name: '黑猫投诉', url: 'https://tousu.sina.com.cn/' },
};

function copyCompany() {
  if (!companyName.value) return;
  uni.setClipboardData({
    data: companyName.value,
    success: () => uni.showToast({ title: '已复制，去网站粘贴搜索', icon: 'none' }),
  });
}

// 无全称态文案：产品定稿（2026-11-03），一字不改。
// 复制内容不加引号、不额外包装：原文自带问号，用户直接粘进聊天框发给 HR。
const ASK_HR_SUB = '还没拿到公司全称。把这句话发给 HR，拿到全称再回来查。';
const ASK_HR_TEXT = '请问贵公司全称是什么？我核实一下公司信息。';

// 复制后按钮变「已复制」并保持 2 秒（产品红线：否则用户会以为没点上反复点）
const askHrCopied = ref(false);
let askHrTimer = null;

function copyAskHr() {
  uni.setClipboardData({
    data: ASK_HR_TEXT,
    success: () => {
      askHrCopied.value = true;
      uni.showToast({ title: '已复制', icon: 'none' });
      if (askHrTimer) clearTimeout(askHrTimer);
      askHrTimer = setTimeout(() => {
        askHrCopied.value = false;
      }, 2000);
    },
  });
}

function openVerifySite(key) {
  const site = VERIFY_SITES[key];
  if (!site) return;
  // 小程序内不能直接打开外部网页（需业务域名），给用户复制网址 + 提示
  uni.showModal({
    title: site.name,
    content: '网址：' + site.url + '\n\n可以复制后到浏览器里打开搜索。',
    confirmText: '复制网址',
    success: (res) => {
      if (res.confirm) {
        uni.setClipboardData({
          data: site.url,
          success: () => uni.showToast({ title: '网址已复制', icon: 'none' }),
        });
      }
    },
  });
}

function sourceLabel(source) {
  return SOURCE_LABEL[source] || '规则命中';
}

// context 拆成「evidence 前 / evidence / evidence 后」，中间那段高亮
function contextBefore(f) {
  const c = String(f.context || '');
  const i = c.indexOf(String(f.evidence));
  return i > 0 ? c.slice(0, i) : '';
}

function contextAfter(f) {
  const c = String(f.context || '');
  const i = c.indexOf(String(f.evidence));
  if (i < 0) return '';
  return c.slice(i + String(f.evidence).length);
}

// 问题区：最多显示 5 条，标题数字随条数变
const MAX_Q = 5;
const allQuestions = computed(() => report.value.questions_to_ask || []);
const shownQuestions = computed(() => allQuestions.value.slice(0, MAX_Q));
const questionTitle = computed(() => {
  const n = allQuestions.value.length;
  if (!n) return '面试前，先问 HR 这几个问题';
  return '面试前，先问 HR 这 ' + Math.min(n, MAX_Q) + ' 个问题';
});

function copyQuestions() {
  const text = allQuestions.value.join('\n');
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: '已复制，可以直接发给 HR', icon: 'none' }),
  });
}

function callPhone(num) {
  uni.makePhoneCall({
    phoneNumber: num,
    fail: () => uni.showToast({ title: '拨号未成功', icon: 'none' }),
  });
}

onMounted(() => {
  const pages = getCurrentPages();
  const current = pages[pages.length - 1];
  const options = (current && current.options) || {};

  const now = new Date();
  const p = (n) => (n < 10 ? '0' + n : '' + n);
  checkTime.value = now.getMonth() + 1 + ' 月 ' + now.getDate() + ' 日 ' + p(now.getHours()) + ':' + p(now.getMinutes());

  // 示例报告：本地数据，不调接口、不扣次数
  if (options.sample === '1') {
    isSample.value = true;
    const which = options.overall || 'red';
    const rep = getExampleReport(which) || getExampleReport('red');
    if (rep) report.value = rep;
    return;
  }

  // 本地识图报告（改造令 §〇）：由首页 runLocal 放进 globalData，不调接口
  if (options.local === '1') {
    const app = getApp();
    const rep = app && app.globalData ? app.globalData.lastReport : null;
    if (rep) {
      report.value = rep;
      isLocalReport.value = true;
      return;
    }
    // 取不到就退回服务端按 task 取；都没有则提示补一张
  }

  // 正常流程：按 task_id 取报告
  const taskId = options.task_id || '';
  if (taskId) {
    fetchAnalysis(taskId)
      .then((res) => {
        if (res.report) report.value = res.report;
      })
      .catch((err) => {
        uni.showToast({ title: (err && err.message) || '报告加载失败', icon: 'none' });
      });
    return;
  }

  // 没有 task_id：用示例数据兜底展示
  const rep = getExampleReport('red');
  if (rep) report.value = rep;
});

onUnmounted(() => {
  if (askHrTimer) clearTimeout(askHrTimer);
});

function gotoFeedback() {
  uni.navigateTo({ url: '/pages/doc/index?type=feedback' });
}

function gotoIndex() {
  uni.switchTab({ url: '/pages/index/index' });
}

// 分享：走平台原生分享（内容见 defineOptions 里的 onShareAppMessage）
function onShare() {
  uni.showToast({ title: '点右上角「…」可以分享给朋友', icon: 'none' });
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background-color: $bg;
  padding-bottom: calc(180rpx + env(safe-area-inset-bottom));
}

// ① 顶部标识
.top-banner {
  padding: 23rpx 39rpx;
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
}

.chip {
  font-size: 21rpx;
  font-weight: 700;
  color: $brand-text;
  background-color: $brand-soft;
  border-radius: 15rpx;
  padding: 5rpx 15rpx;
  margin-right: 12rpx;
}

.chip-sample {
  color: $ink-2;
  background-color: $surface-2;
}

.main {
  padding: 0 39rpx;
  display: flex;
  flex-direction: column;
}

// ② 结论区：26px 圆角 = 24px 设计稿 → 46rpx
.verdict {
  border-radius: 50rpx;
  padding: 42rpx 38rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
  border: 2rpx solid $line;
}

.verdict-red {
  background-color: $red-soft;
  border-color: $red-soft;
}

.verdict-amber {
  background-color: $amber-soft;
  border-color: $amber-soft;
}

.verdict-green {
  background-color: $green-soft;
  border-color: $green-soft;
}

.verdict-unknown {
  background-color: $surface;
}

// 竖排三灯
.pole {
  width: 96rpx;
  padding: 19rpx 0;
  border-radius: 48rpx;
  background-color: $housing;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-right: 35rpx;
  flex-shrink: 0;
}

.pole-lamp {
  width: 58rpx;
  height: 58rpx;
  border-radius: 50%;
  background-color: $off;
  opacity: 0.4;

  & + & {
    margin-top: 15rpx;
  }

  &.on {
    opacity: 1;
  }
}

.pole-lamp:nth-child(1).on {
  background-color: $red;
  box-shadow: 0 0 30rpx $red;
}

.pole-lamp:nth-child(2).on {
  background-color: $amber;
  box-shadow: 0 0 30rpx $amber;
}

.pole-lamp:nth-child(3).on {
  background-color: $green;
  box-shadow: 0 0 30rpx $green;
}

.verdict-text {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.verdict-title {
  font-size: 50rpx;
  font-weight: 900;
  line-height: 1.28;
  color: $ink;
}

.verdict-sub {
  margin-top: 15rpx;
  font-size: 25rpx;
  color: $ink-2;
}

.basis {
  margin-top: 23rpx;
  font-size: 23rpx;
  color: $ink-2;
}

// 区块标题 17px → 33rpx，800
.h2 {
  margin-top: 54rpx;
  margin-bottom: 23rpx;
  font-size: 33rpx;
  font-weight: 800;
  color: $ink;
  display: block;
}

.h2row {
  margin-top: 54rpx;
  margin-bottom: 23rpx;
  display: flex;
  flex-direction: row;
  align-items: baseline;
  justify-content: space-between;

  .h2 {
    margin: 0;
  }
}

.h2-side {
  font-size: 23rpx;
  color: $ink-2;
}

// ④ 6 项检查：2 列网格
.dims {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  margin-right: -19rpx;
}

.dim {
  width: calc(50% - 19rpx);
  margin-right: 19rpx;
  margin-bottom: 19rpx;
  background-color: $surface;
  border-radius: 31rpx;
  padding: 27rpx;
  box-sizing: border-box;
}

.dim-head {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.dim-name {
  margin-left: 15rpx;
  font-size: 27rpx;
  font-weight: 700;
  color: $ink;
}

.dim-short {
  margin-top: 12rpx;
  font-size: 25rpx;
  color: $ink-3;
  display: block;
}

.dim-none {
  color: $off-text;
}

.card {
  background-color: $surface;
  border-radius: 38rpx;
}

// ⑤ findings
.finding {
  margin-bottom: 19rpx;
  padding: 31rpx;
}

.finding-head {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.finding-title {
  flex: 1;
  margin-left: 15rpx;
  font-size: 31rpx;
  font-weight: 800;
  color: $ink;
}

.source-tag {
  font-size: 21rpx;
  font-weight: 700;
  border-radius: 15rpx;
  padding: 5rpx 15rpx;

  &.src-rule {
    color: $red-text;
    background-color: $red-soft;
  }

  &.src-pattern {
    color: $amber-text;
    background-color: $amber-soft;
  }

  &.src-llm {
    color: $brand-text;
    background-color: $brand-soft;
  }
}

// 原话引用框
.quote {
  margin-top: 23rpx;
  background-color: $surface-2;
  border-radius: 23rpx;
  padding: 23rpx;
  border-left: 6rpx solid $line;
}

.quote-red {
  border-left-color: $red;
}

.quote-amber {
  border-left-color: $amber;
}

.quote-green {
  border-left-color: $green;
}

.quote-text {
  font-size: 27rpx;
  line-height: 1.7;
  color: $ink-3;
}

// evidence 高亮：用对应灯的 -mark 色
.quote-mark {
  font-size: 27rpx;
  line-height: 1.7;
  font-weight: 700;
  color: $ink;
  border-radius: 6rpx;
}

.mark-red {
  background-color: $red-mark;
}

.mark-amber {
  background-color: $amber-mark;
}

.mark-green {
  background-color: $green-mark;
}

.reason {
  margin-top: 23rpx;
  font-size: 27rpx;
  line-height: 1.7;
  color: $ink-3;
  display: block;
}

.empty-findings {
  padding: 46rpx 31rpx;
}

.empty-t {
  font-size: 27rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}

// ⑥ 问题清单
.qlist {
  padding: 23rpx 31rpx 31rpx;
}

.q-item {
  display: flex;
  flex-direction: row;
  margin-top: 23rpx;
}

.q-index {
  width: 38rpx;
  height: 38rpx;
  border-radius: 50%;
  background-color: $brand-soft;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 19rpx;
  flex-shrink: 0;
  margin-top: 4rpx;
}

.q-num {
  font-size: 21rpx;
  font-weight: 700;
  color: $brand-text;
}

.q-text {
  flex: 1;
  font-size: 27rpx;
  line-height: 1.6;
  color: $ink-3;
}

.btn-copy {
  margin-top: 31rpx;
  height: 85rpx;
  border-radius: 27rpx;
  border: 3rpx solid $outline;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 29rpx;
    font-weight: 700;
    color: $ink;
  }
}

// ⑦ 核实方法
.vlist {
  padding: 23rpx 31rpx;
}

.v-item {
  display: flex;
  flex-direction: row;
  margin-top: 19rpx;
}

.v-dot {
  width: 14rpx;
  height: 14rpx;
  border-radius: 50%;
  background-color: $green;
  margin-right: 19rpx;
  margin-top: 14rpx;
  flex-shrink: 0;
}

.v-text {
  flex: 1;
  font-size: 27rpx;
  line-height: 1.7;
  color: $ink-3;
}

// ⑦b 公司核实卡
.corp-card {
  margin-top: 19rpx;
  padding: 31rpx;
}

.corp-head {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.corp-title {
  font-size: 31rpx;
  font-weight: 800;
  color: $ink;
}

.corp-tag {
  font-size: 21rpx;
  color: $ink-2;
  background-color: $surface-2;
  border-radius: 15rpx;
  padding: 4rpx 15rpx;
}

.corp-name-row {
  margin-top: 23rpx;
  background-color: $surface-2;
  border-radius: 23rpx;
  padding: 23rpx;
}

.corp-name {
  font-size: 31rpx;
  font-weight: 700;
  color: $ink;
  line-height: 1.5;
}

.corp-copy {
  margin-top: 19rpx;
  height: 85rpx;
  border-radius: 27rpx;
  border: 3rpx solid $outline;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 27rpx;
    font-weight: 700;
    color: $ink;
  }
}

.corp-tip {
  margin-top: 19rpx;
  font-size: 23rpx;
  line-height: 1.6;
  color: $ink-2;
  display: block;
}

.corp-links {
  margin-top: 23rpx;
}

.corp-link {
  padding: 23rpx 0;
  border-bottom: 2rpx solid $divider;

  &.corp-link-last {
    border-bottom: none;
    padding-bottom: 0;
  }
}

.corp-link-t {
  font-size: 27rpx;
  font-weight: 700;
  color: $brand-text;
  display: block;
}

.corp-link-s {
  margin-top: 6rpx;
  font-size: 23rpx;
  color: $ink-2;
  display: block;
}

// ⑧ 已经交了钱
.money-card {
  margin-top: 54rpx;
  background-color: $red-soft;
  padding: 35rpx 31rpx;
}

.money-title {
  font-size: 33rpx;
  font-weight: 900;
  color: $red-text;
  display: block;
}

.money-body {
  margin-top: 15rpx;
  font-size: 27rpx;
  line-height: 1.7;
  color: $ink-3;
  display: block;
}

.money-btns {
  margin-top: 31rpx;
  display: flex;
  flex-direction: row;
}

.btn-line {
  flex: 1;
  height: 92rpx;
  border-radius: 27rpx;
  border: 3rpx solid $red;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 29rpx;
    font-weight: 700;
    color: $red-text;
  }
}

.btn-line-gap {
  margin-left: 19rpx;
}

// 12333 单独一行，占满宽度
// 12333 只做文字提示，不做拨号键（D21）
.labour-tip {
  margin-top: 23rpx;
  background-color: $surface-2;
  border-radius: 19rpx;
  padding: 19rpx 23rpx;
}

.labour-tip-text {
  font-size: 23rpx;
  line-height: 1.6;
  color: $ink-3;
}

.help-lines {
  margin-top: 27rpx;
}

.help-line {
  display: flex;
  flex-direction: row;
  margin-top: 15rpx;
}

.help-dot {
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  background-color: $red;
  margin-right: 15rpx;
  margin-top: 14rpx;
  flex-shrink: 0;
}

.help-text {
  flex: 1;
  font-size: 25rpx;
  line-height: 1.7;
  color: $ink-3;
}

// ⑨ 免责声明
.disclaimer-box {
  margin-top: 54rpx;
  padding: 31rpx;
  background-color: $surface-2;
  border-radius: 31rpx;
}

.disclaimer {
  font-size: 23rpx;
  line-height: 1.7;
  color: $ink-2;
  display: block;
}

.model-line {
  margin-top: 15rpx;
  font-size: 21rpx;
  color: $off-text;
  display: block;
}

.inaccurate {
  margin-top: 23rpx;
  height: 85rpx;
  border-radius: 27rpx;
  border: 3rpx solid $outline;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 27rpx;
    font-weight: 700;
    color: $ink-3;
  }
}

// ⑩ 底部固定按钮
.bottom-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: $surface;
  border-top: 2rpx solid $line;
  padding: 23rpx 39rpx calc(23rpx + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: row;
}

.btn-share {
  flex: 1;
  height: 100rpx;
  border-radius: 31rpx;
  border: 3rpx solid $outline;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 19rpx;

  text {
    font-size: 31rpx;
    font-weight: 700;
    color: $ink;
  }
}

.btn-primary {
  flex: 1;
  height: 100rpx;
  border-radius: 31rpx;
  background-color: $cta;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 31rpx;
    font-weight: 900;
    color: $cta-ink;
  }
}
</style>
