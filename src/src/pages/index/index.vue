<template>
  <view class="page">
    <!-- 自定义导航栏：品牌名只在这里出现一次（任务书 §3 bug 修复） -->
    <NavBar brand />

    <view class="main">
      <text class="hero-title">去面试之前，{{ '\n' }}先让我看一眼</text>
      <text class="hero-sub">{{ VISION_ENGINE ? '招聘截图发过来，30 秒告诉你这份工作有没有坑。' : '把招聘信息粘贴过来，马上告诉你这份工作有没有坑。' }}</text>

      <!-- 规则版（提审用）：粘贴卡（双版本令第二节第 2 条）。
           全部在手机上跑，不做手机认字，所以主操作是「粘贴文字」而不是上传截图。 -->
      <view v-if="!VISION_ENGINE" class="card upload upload-card paste-card">
        <textarea
          v-model="pasteText"
          class="paste-input"
          :maxlength="PASTE_MAX"
          placeholder="把招聘信息或和 HR 的聊天，整段粘贴到这里"
          placeholder-class="paste-ph"
          :show-confirm-bar="false"
          :adjust-position="true"
          disable-default-padding
        />
        <view class="paste-bar">
          <view class="paste-btn" @tap="onPasteClipboard">
            <text>一键粘贴</text>
          </view>
          <text class="paste-count t3" :class="{ 'paste-count-over': pasteOver }">{{ pasteText.length }}/{{ PASTE_MAX }}</text>
          <view v-if="pasteText" class="paste-clear" @tap="clearPaste">
            <text>清空</text>
          </view>
        </view>
        <text v-if="pasteOver" class="paste-tip">最多 3000 字，已截断</text>

        <view class="btn-primary" :class="{ 'btn-primary-disabled': !pasteText.trim(), 'btn-busy': submitting }" @tap="onPickOrStart">
          <text>{{ buttonText }}</text>
        </view>

        <view class="up-meta">
          <text v-if="isUnlimited">内测期间不限次数</text>
          <text v-else>还能免费查 <text class="up-meta-num">{{ balance }}</text> 次</text>
          <text>岗位介绍和 HR 聊天一起贴，查得更准</text>
        </view>
      </view>

      <!-- 上传卡（识图版专用）：抽成组件，规则版不 import 它，
           所以规则版产物里不会出现「点这里选截图」这类上传文案 -->
      <UploadCard
        v-else
        :images="images"
        :submitting="submitting"
        :balance="balance"
        :is-unlimited="isUnlimited"
        :max-images="3"
        @pick="chooseImages"
        @remove="removeImage"
        @start="onPickOrStart"
      />

      <!-- 示例报告入口：内置数据，不扣次数 -->
      <view class="card demo" @tap="openSampleReport">
        <view class="icon-box">
          <view class="ico-eye"></view>
        </view>
        <view class="grow">
          <text class="demo-t">没有内容？先看一份示例报告</text>
          <text class="demo-s">看看检查结果长什么样，不扣次数</text>
        </view>
        <view class="chev"></view>
      </view>

      <!-- 信号灯说明 -->
      <text class="h2">每份报告，逐项给你亮灯</text>
      <view class="signal">
        <view class="signal-item">
          <SignalLamp level="red" size="lg" />
          <text class="signal-n">红灯</text>
          <text class="signal-d">建议别去</text>
        </view>
        <view class="signal-item">
          <SignalLamp level="amber" size="lg" />
          <text class="signal-n">黄灯</text>
          <text class="signal-d">先问清楚再去</text>
        </view>
        <view class="signal-item">
          <SignalLamp level="green" size="lg" />
          <text class="signal-n">绿灯</text>
          <text class="signal-d">这一项没问题</text>
        </view>
      </view>

      <!-- 套路库里最近常见的（mock 数据，等后端接口） -->
      <view class="h2row">
        <text class="h2">套路库里，最近常见的</text>
      </view>
      <view class="card list">
        <view v-for="(p, idx) in patterns" :key="p.id" class="row" :class="{ 'row-last': idx === patterns.length - 1 }">
          <SignalLamp :level="p.level" size="sm" />
          <view class="grow">
            <text class="row-t">{{ p.t }}</text>
            <text class="row-s">{{ p.s }}</text>
          </view>
          <text class="tag" :class="'tag-' + p.level">{{ p.level === 'red' ? '红灯' : '黄灯' }}</text>
        </view>
      </view>

      <!-- 服务说明入口（派书 §3 首页必须有；设计稿没画，做成低调一行，不抢主视觉） -->
      <view class="ai-notice-row" @tap="gotoAiDoc">
        <text class="ai-notice-text">{{ VISION_ENGINE ? '本服务根据截图文字和规则库自动检查，查看检查规则说明' : '本服务根据你提供的文字和规则库自动检查，查看检查规则说明' }}</text>
        <view class="ai-notice-chev"></view>
      </view>

      <text class="disclaimer">{{ disclaimer }}</text>
    </view>

    <!-- 次数用完弹窗 -->
    <!-- D39：会员关闭时 member-available=false，弹窗里整块会员卡与价格都不渲染，
         只剩「看广告换 1 次」和「明天再来」 -->
    <QuotaSheet
      :visible="showQuota"
      :remaining-ad="adRemaining"
      :ad-cap="adCap"
      :member-available="memberAvailable"
      :weekly-price="weeklyPrice"
      :ad-loading="adLoading"
      @close="showQuota = false"
      @watch-ad="onWatchAd"
      @open-member="gotoMember"
    />
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import NavBar from '@/components/NavBar.vue';
import SignalLamp from '@/components/SignalLamp.vue';
import QuotaSheet from '@/components/QuotaSheet.vue';
// 上传卡只在识图版首页渲染。规则版构建时 vite.config.js 会把这个路径
// 别名指向一个空组件（UploadCard.stub.vue），所以规则版产物里不会出现
// 「点这里选截图」这类上传文案——自检脚本会逐词核对。
import UploadCard from '@/components/UploadCard.vue';
import { ensureLogin, getUser, refreshUser } from '@/services/session.js';
import { createAnalysis, uploadImage, claimAdReward, newRequestId, ApiError } from '@/services/api.js';
// 改造令 §〇：截图直发 DeepSeek 识图（失败静默退回上面的服务器流程）
// 双版本令第三节：规则版不得包含 DeepSeek 相关代码。做法是在 vite.config.js 里把整个
// judge.js 换成空实现（引擎为 rules 时），规则版包里因此不会出现提示词、接口地址和模型名；
// 构建后另有脚本逐词扫产物兜底。
import { isVisionJudgeAvailable, toBase64, judgeImages, validateHits } from '@/services/judge.js';
import { buildLocalReport } from '@/services/localReport.js';
import { buildRuleReport } from '@/services/rules.js';
// 规则版不做手机认字（双版本令修订），ocr.js 这一版不接进首页。
import { DEEPSEEK_MAX_IMAGES, MIN_OCR_CHARS, QUOTA_RULES, VISION_ENGINE } from '@/common/config.js';
import { runRewardedFlow, canTriggerAd } from '@/common/adGuard.js';
import { canBuyMember, isMembershipVisible } from '@/common/entitlement.js';
import { getAdUnitId } from '@/common/config.js';
import { isUnlimitedEnv } from '@/common/env.js';
import { saveHistory } from '@/services/history.js';
import { reportStats } from '@/services/stats.js';
import { DISCLAIMER_TEXT } from '@/common/constants.js';
import { SHARE_TITLE } from '@/common/brand.js';

defineOptions({
  name: 'IndexPage',
  // 首页分享：标题不带任何公司名（合规 §8）
  onShareAppMessage() {
    return { title: SHARE_TITLE, path: '/pages/index/index' };
  },
});

const images = ref([]);
// 规则版：粘贴的招聘文字（双版本令第二节第 2 条）。最多 3000 字，超出截断并提示。
const PASTE_MAX = 3000;
const pasteText = ref('');
const pasteOver = ref(false);
const submitting = ref(false);
const balance = ref(0);
// 规则版没有广告位（流量主未开通）：初始 0，次数用完弹窗里就不出现「看广告换 1 次」
const adRemaining = ref(VISION_ENGINE ? 5 : 0);
const adCap = ref(5);
const adLoading = ref(false);
const showQuota = ref(false);
// 开发版/体验版不限次数（老板 2026-11-04 定）：只在模板上用，不参与扣次数逻辑
const isUnlimited = computed(() => isUnlimitedEnv());
const memberAvailable = ref(canBuyMember());
const weeklyPrice = ref('6.9');
const disclaimer = DISCLAIMER_TEXT;

// 套路库「最近常见」：等后端 pattern_hits 接口，先用 mock（任务书 §6.1 允许）
const patterns = ref([
  { id: 'p1', level: 'red', t: '「先交 300 元服装费，入职后退」', s: '入职前就收钱，正规公司不会这么做' },
  { id: 'p2', level: 'amber', t: '「储备干部，负责电话回访客户」', s: '名字好听，实际可能是电话销售' },
  { id: 'p3', level: 'red', t: '「零基础包就业，学费可以分期」', s: '招聘变成卖课，小心背上培训贷' },
]);

const buttonText = computed(() => {
  if (submitting.value) return '正在检查…';
  // 规则版（粘贴文字）：没内容时写「粘贴文字，开始检查」，有内容时写「开始检查」
  if (!VISION_ENGINE) return pasteText.value.trim() ? '开始检查' : '粘贴文字，开始检查';
  if (images.value.length) return '开始检查（' + images.value.length + ' 张）';
  return '选截图，开始检查';
});

function syncUser(user) {
  if (!user) return;
  balance.value = Number((user.quota && user.quota.balance) || 0);
  if (user.ad) {
    if (user.ad.daily_cap) adCap.value = Number(user.ad.daily_cap);
    if (typeof user.ad.remaining_today === 'number') adRemaining.value = Number(user.ad.remaining_today);
  }
  // 本地识图路径可用时，次数以本地为准：否则会出现「显示 3 次、实际已用掉」的矛盾
  if (isVisionJudgeAvailable()) balance.value = localFreeLeft();
  // 规则版：没有服务器，次数一律取本地
  if (!VISION_ENGINE) balance.value = localFreeLeft();
  // 开发版/体验版不限次数：模板用 isUnlimited 显示「内测期间不限次数」，
  // 这里给一个足够大的数，避免后续任何 <= 0 的判断误拦
  if (isUnlimitedEnv()) balance.value = 999999;
}

// 纯本地路径下不能显示「还能免费查 0 次」就拦住检查，次数由本地控制
// 规则版全本地；DeepSeek 版有密钥时也走全本地
function localPathActive() {
  if (!VISION_ENGINE) return true;
  return isVisionJudgeAvailable();
}

// 规则版（提审用）不与任何服务器通信：不登录、不拉用户信息、不上报。
// 双版本令第二节第 2 条：规则版「不调服务器、不调云托管、不调云 OCR、不调 DeepSeek」。
onMounted(() => {
  if (!VISION_ENGINE) {
    // 纯本地：次数直接取本地，不发起任何请求
    balance.value = isUnlimitedEnv() ? 999999 : localFreeLeft();
    return;
  }
  ensureLogin()
    .then((u) => {
      syncUser(u);
      return refreshUser();
    })
    .then(syncUser)
    .catch(() => {});
});

onShow(() => {
  if (!VISION_ENGINE) {
    balance.value = isUnlimitedEnv() ? 999999 : localFreeLeft();
    return;
  }
  if (getUser()) refreshUser().then(syncUser).catch(() => {});
});

// 上传卡整张都能点（老板 2026-11-05 双版本令第四节第 3 条）：
// 卡里已选图时点空白处继续加图，没选图时点卡选图；按钮和缩略图各自有 stop 处理。
function onPickCard() {
  if (submitting.value) return;
  if (images.value.length < 3) chooseImages();
}

// 一键粘贴：**用户点了按钮才读剪贴板**，绝不进页面就读（双版本令第二节第 2 条）。
// 剪贴板用途已写进隐私政策与后台「用户隐私保护指引」说明。
function onPasteClipboard() {
  uni.getClipboardData({
    success: (res) => {
      const data = String((res && res.data) || '');
      if (!data) {
        uni.showToast({ title: '剪贴板是空的，先把招聘文字复制下来', icon: 'none' });
        return;
      }
      setPasteText(data);
    },
    fail: () => {
      uni.showToast({ title: '没读到剪贴板，请手动粘贴', icon: 'none' });
    },
  });
}

function setPasteText(raw) {
  const s = String(raw || '');
  if (s.length > PASTE_MAX) {
    pasteText.value = s.slice(0, PASTE_MAX);
    pasteOver.value = true;
    uni.showToast({ title: '最多 3000 字，已截断', icon: 'none' });
    return;
  }
  pasteText.value = s;
  pasteOver.value = false;
}

function clearPaste() {
  pasteText.value = '';
  pasteOver.value = false;
}

// 主按钮：
//   规则版 —— 没内容不响应（按钮是灰的）；有内容先查次数，再检查
//   DeepSeek 版 —— 没选图先选图，选了图就开始检查
function onPickOrStart() {
  if (submitting.value) return;
  if (!VISION_ENGINE) {
    if (!pasteText.value.trim()) return; // 没内容时按钮灰着，不弹窗打扰
    // 次数为 0 时点按钮，弹「次数用完」（双版本令第二节第 2 条）
    if (!isUnlimitedEnv() && localFreeLeft() <= 0) {
      showQuota.value = true;
      return;
    }
    startAnalysis();
    return;
  }
  if (!images.value.length) {
    chooseImages();
    return;
  }
  // 本地识图路径可用时次数以本地为准
  const left = localPathActive() ? localFreeLeft() : balance.value;
  // 开发版/体验版不限次数：不拦、不弹「次数用完」
  if (!isUnlimitedEnv() && left <= 0) {
    showQuota.value = true;
    return;
  }
  startAnalysis();
}

function chooseImages() {
  const remain = 3 - images.value.length;
  if (remain <= 0) return;
  uni.chooseImage({
    count: remain,
    sizeType: ['compressed'],
    sourceType: ['album', 'camera'],
    success: (res) => {
      (res.tempFilePaths || []).slice(0, remain).forEach((p) => {
        if (images.value.length < 3) images.value.push({ path: p, hash: p });
      });
    },
  });
}

function removeImage(idx) {
  images.value.splice(idx, 1);
}

function startAnalysis() {
  submitting.value = true;
  // 规则版（提审用）：全手机本地，不碰服务器。DeepSeek 版沿用原流程。
  if (!VISION_ENGINE) {
    runRulePath();
    return;
  }
  runLocalThenFallback();
}

// 规则版主流程（双版本令第二节，修订后不做手机认字）：
//   粘贴文字 → 文本规整 → 关键词规则 + 套路匹配 → 拼报告 → 报告页
// 全程在手机上，不发任何请求。不是招聘内容时不扣次数。
async function runRulePath() {
  const text = String(pasteText.value || '');
  try {
    const t0 = Date.now();
    const { report, meta } = buildRuleReport(text, { minChars: MIN_OCR_CHARS });
    meta.elapsed_ms = Date.now() - t0;
    submitting.value = false;
    if (!report.is_job_posting) {
      // 不是招聘内容：提示但不扣次数（双版本令第二节第 1 条原文）
      uni.showToast({
        title: '没看出是招聘信息，把岗位介绍或和 HR 的聊天整段粘贴进来',
        icon: 'none',
        duration: 3000,
      });
      return;
    }
    // 扣次数：只扣真正的招聘检查
    setLocalFreeLeft(localFreeLeft() - 1);
    saveHistory(report, {
      schemeTitle: (meta.scheme && meta.scheme.title) || '',
      schemeId: meta.scheme_id || '',
      patterns: (report.findings || []).map((f) => f.pattern_id).filter(Boolean),
    });
    const app = getApp();
    if (app && app.globalData) {
      app.globalData.lastReport = report;
      app.globalData.lastReportMeta = meta;
    }
    if (isJobUnlimited()) balance.value = 999999;
    else balance.value = localFreeLeft();
    uni.navigateTo({ url: '/pages/report/index?local=1' });
  } catch (e) {
    submitting.value = false;
    uni.showToast({ title: '检查没做完，次数没扣，请再试一次', icon: 'none' });
  }
}

// 规则版没有服务器，次数一律以本地为准；开发版/体验版仍不限次数
function isJobUnlimited() {
  return isUnlimitedEnv();
}

// 新路径（改造令 §〇）：截图直发 DeepSeek 识图，一次完成认字 + 判断。
// 任何一步失败都返回 null，静默走原来的服务器流程（用户无感知）。
// 双版本令：这段只在 DeepSeek 版编译进包，规则版产物里一个字都不留。
async function runLocal(paths) {
  if (!isVisionJudgeAvailable()) return null;
  try {
    const images = [];
    for (let i = 0; i < paths.length && i < DEEPSEEK_MAX_IMAGES; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      const b64 = await toBase64(paths[i]);
      if (!b64) return null;
      images.push(b64);
    }
    if (!images.length) return null;
    const { raw } = await judgeImages(images);
    const text = String((raw && raw.text) || '');
    if (text.replace(/\s/g, '').length < MIN_OCR_CHARS) return null; // 没认出来
    const hits = validateHits(raw, text);
    // 返回 { report, meta }：report 严格符合服务器 schema，meta 放排查信息
    return buildLocalReport(raw, hits, text, { minChars: MIN_OCR_CHARS });
  } catch (e) {
    // 超时/余额不足/网络/JSON 坏：一律退回旧流程
    return null;
  }
}

// 本地次数（改造令 §7）：内测期记在手机，默认 3 次。
// 注意：不能用 parseInt(x) || 3 —— 剩 0 次时 0 是假值，会被误当成 3。
function localFreeLeft() {
  try {
    const raw = uni.getStorageSync('qbl_free_left');
    if (raw === '' || raw === null || raw === undefined) return QUOTA_RULES.newUserFree;
    const n = parseInt(raw, 10);
    return Number.isNaN(n) ? QUOTA_RULES.newUserFree : Math.max(0, n);
  } catch (e) {
    return QUOTA_RULES.newUserFree;
  }
}

function setLocalFreeLeft(n) {
  try {
    uni.setStorageSync('qbl_free_left', String(Math.max(0, n)));
  } catch (e) {
    /* 存储失败不影响出报告 */
  }
}

// 双版本令：退回服务器流程只在 DeepSeek 版里编进包（规则版没有服务器，不能有任何退回路径）
async function runLocalThenFallback() {
  const paths = images.value.map((i) => i.path);
  let local = null;
  try {
    local = await runLocal(paths);
  } catch (e) {
    local = null;
  }
  if (local && local.report) {
    submitting.value = false;
    // 扣次数：只扣真正做了检查的（is_job_posting=false 不扣）
    if (local.report.is_job_posting) setLocalFreeLeft(localFreeLeft() - 1);
    const meta = local.meta || {};
    // 存本地检查记录（7 天 / 50 条，不存截图）
    saveHistory(local.report, {
      schemeTitle: (meta.scheme && meta.scheme.title) || '',
      schemeId: meta.scheme_id || '',
      patterns: (local.report.findings || []).map((f) => f.pattern_id).filter(Boolean),
    });
    // 匿名上报（不带文字/截图/身份），失败不影响用户
    reportStats(local.report.overall, {
      patternIds: (local.report.findings || []).map((f) => f.pattern_id).filter(Boolean),
      schemeId: meta.scheme_id || '',
    });
    const app = getApp();
    if (app && app.globalData) {
      app.globalData.lastReport = local.report;
      app.globalData.lastReportMeta = meta; // 含 ocr_text 与 scheme，用于横幅与核对
    }
    uni.navigateTo({ url: '/pages/report/index?local=1' });
    return;
  }
  // 退回服务器流程
  ensureLogin()
    .then(() => uploadAll(paths))
    .then((imageIds) =>
      createAnalysis({
        imageIds,
        files: images.value.map((i) => ({ hash: i.hash })),
        idemKey: newRequestId(),
        filePath: images.value[0].path,
      })
    )
    .then((res) => {
      submitting.value = false;
      if (res.quota && typeof res.quota.balance === 'number') balance.value = res.quota.balance;
      if (res.dedupe_hit && res.report) {
        uni.navigateTo({ url: '/pages/report/index?report_id=' + res.report.report_id });
        return;
      }
      if (res.status !== 'pending' && res.status !== 'running') {
        uni.showToast({ title: '服务返回状态异常，请稍后到「我的」查看', icon: 'none' });
        return;
      }
      uni.navigateTo({ url: '/pages/analyzing/index?task_id=' + res.task_id });
    })
    .catch((err) => {
      submitting.value = false;
      handleError(err);
    });
}

async function uploadAll(paths) {
  const ids = [];
  for (let i = 0; i < paths.length; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const up = await uploadImage(paths[i]);
    if (up && up.image_id) ids.push(up.image_id);
  }
  if (!ids.length) throw new ApiError('VALIDATION_ERROR', '截图上传失败，请重试');
  return ids;
}

function handleError(err) {
  const code = err instanceof ApiError ? err.code : 'INTERNAL_ERROR';
  if (code === 'QUOTA_EXHAUSTED') {
    // 开发版/体验版不限次数：不弹次数用完的窗口
    if (!isUnlimitedEnv()) showQuota.value = true;
    return;
  }
  const tips = {
    VALIDATION_ERROR: '截图不符合要求，请重新选择',
    RATE_LIMITED: '操作太频繁了，请稍后再试',
    CONTENT_BLOCKED: '图片未通过内容安全检测，请换一张',
    ANALYSIS_UNAVAILABLE: '服务暂时不可用，请稍后再试（次数未扣）',
    ANALYSIS_FAILED: '检查失败，请稍后再试（次数未扣）',
    UNAUTHORIZED: '登录已过期，请重新进入小程序',
  };
  uni.showToast({ title: tips[code] || (err && err.message) || '上传失败，请重试', icon: 'none' });
}

// 示例报告：内置数据，不调接口、不扣次数
// 按任务书 §9「4 种 overall 各截一张」的要求，这里能直达四种形态
function openSampleReport() {
  const overalls = ['red', 'amber', 'green', 'unknown'];
  uni.showActionSheet({
    itemList: ['看红灯的示例', '看黄灯的示例', '看绿灯的示例', '看信息不足的示例'],
    success: (res) => {
      const which = overalls[res.tapIndex] || 'red';
      uni.navigateTo({ url: '/pages/report/index?sample=1&overall=' + which });
    },
    fail: () => {
      // 用户取消就不动
    },
  });
}

// 看广告换次数：用户点了按钮才创建广告（§6.2）
// 规则版没有广告位（流量主未开通），按钮不渲染，这里也直接返回，不发任何请求。
function onWatchAd() {
  if (!VISION_ENGINE) return;
  if (adLoading.value) return;
  if (!canTriggerAd('index')) {
    uni.showToast({ title: '操作太频繁了，请稍后再试', icon: 'none' });
    return;
  }
  adLoading.value = true;
  const requestId = newRequestId();
  runRewardedFlow('index')
    .then((res) => {
      let result = 'completed';
      if (res.fallback) result = 'no_fill';
      else if (!res.watched) result = 'error';
      return claimAdReward({ requestId, adUnitId: getAdUnitId(), result }).then((data) => {
        if (data.quota && typeof data.quota.balance === 'number') balance.value = data.quota.balance;
        if (typeof data.remaining_today === 'number') adRemaining.value = data.remaining_today;
        if (data.granted) {
          uni.showToast({ title: res.fallback ? '广告没加载出来，已送你 1 次' : '已增加 1 次', icon: 'none' });
          showQuota.value = false;
        } else if (data.reason === 'daily_cap_reached') {
          uni.showToast({ title: '今天看广告换次数的机会用完了', icon: 'none' });
        } else {
          uni.showToast({ title: '没有拿到次数，请稍后再试', icon: 'none' });
        }
      });
    })
    .catch((err) => {
      uni.showToast({ title: (err && err.message) || '领取失败，请稍后再试', icon: 'none' });
    })
    .then(() => {
      adLoading.value = false;
    });
}

function gotoMember() {
  // D39：会员关闭时不做任何跳转（页面上也点不到，这里兜底防误触发）
  if (!isMembershipVisible()) return;
  showQuota.value = false;
  uni.navigateTo({ url: '/pages/member/index' });
}

// 服务说明入口 → 检查规则说明页（和「我的」页同一个页面）
function gotoAiDoc() {
  uni.navigateTo({ url: '/pages/doc/index?type=ai' });
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background-color: $bg;
}

// 页面左右 20 设计稿 → 39rpx；底部留出 tab 高度 + 安全区
.main {
  padding: 0 39rpx;
  padding-bottom: calc(40rpx + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
}

.hero-title {
  margin-top: 54rpx;
  font-size: 65rpx;
  line-height: 1.24;
  font-weight: 900;
  color: $ink;
  letter-spacing: -1rpx;
  white-space: pre-line;
}

.hero-sub {
  margin-top: 23rpx;
  font-size: 29rpx;
  line-height: 1.6;
  color: $ink-2;
}

.card {
  background-color: $surface;
  border-radius: 38rpx;
}

.upload {
  margin-top: 46rpx;
  border-radius: 46rpx;
  padding: 38rpx;
}

// 上传卡（老板 2026-11-05 双版本令第四节第 3 条）：整张卡都能点，虚线框
.upload-card {
  // 虚线框用 dashed border，颜色沿用已有的 $off
  border: 3rpx dashed $off;
}
.upload-dashed {
  display: block;
}
// 选图后缩略图独占内容区
.thumbs-in-card {
  margin-top: 0;
  margin-bottom: 19rpx;
}
.thumb-add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2rpx dashed $off;
  background: $surface-2;
}
.thumb-add-plus {
  font-size: 44rpx;
  line-height: 1;
  color: $ink-2;
}
.thumb-add-t {
  margin-top: 8rpx;
  font-size: 21rpx;
  color: $ink-2;
}

// 粘贴卡（规则版首页，双版本令第二节第 2 条）：样式与上传卡保持一致
.paste-card {
  border: 3rpx dashed $off;
}
.paste-input {
  width: 100%;
  min-height: 260rpx;
  font-size: 29rpx;
  line-height: 1.6;
  color: $ink;
  background: $surface-2;
  border-radius: $radius-sm;
  padding: 23rpx;
  box-sizing: border-box;
}
.paste-ph {
  color: $ink-2;
  font-size: 29rpx;
}
.paste-bar {
  display: flex;
  flex-direction: row;
  align-items: center;
  margin-top: 19rpx;
}
.paste-btn {
  padding: 13rpx 27rpx;
  border-radius: $radius-tag;
  border: 2rpx solid $off;
  font-size: 25rpx;
  color: $ink-3;
}
.paste-count {
  flex: 1;
  text-align: right;
}
.paste-count-over {
  color: $amber-text;
}
.paste-clear {
  margin-left: 23rpx;
  padding: 13rpx 19rpx;
  font-size: 25rpx;
  color: $ink-2;
}
.paste-tip {
  display: block;
  margin-top: 12rpx;
  font-size: 23rpx;
  color: $amber-text;
}
// 主按钮灰掉态：没内容时不可点，视觉上要能一眼看出
.btn-primary-disabled {
  opacity: 0.45;
}

// 插画区：设计稿 128 高 → 246rpx
.illus {
  position: relative;
  height: 246rpx;
  border-radius: 31rpx;
  background-color: $surface-2;
  overflow: hidden;
}

.shot {
  position: absolute;
  border-radius: 19rpx;
  background-color: $surface;
  border: 3rpx solid $line;
  box-sizing: border-box;

  &.l {
    left: 161rpx;
    top: 50rpx;
    width: 127rpx;
    height: 215rpx;
    transform: rotate(-9deg);
  }

  &.r {
    left: 445rpx;
    top: 50rpx;
    width: 127rpx;
    height: 215rpx;
    transform: rotate(9deg);
  }

  &.m {
    left: 284rpx;
    top: 27rpx;
    width: 150rpx;
    height: 242rpx;
    border: 4rpx solid $ink;
    border-radius: 23rpx;
    padding: 27rpx 19rpx;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
  }
}

.bar-line {
  height: 12rpx;
  border-radius: 6rpx;
  background-color: $line;
  margin-bottom: 13rpx;

  &.hit {
    height: 19rpx;
    background-color: $red-mark;
  }
}

.bang {
  position: absolute;
  left: 407rpx;
  top: 12rpx;
  width: 46rpx;
  height: 46rpx;
  border-radius: 50%;
  background-color: $red;
  color: $ink;
  font-size: 29rpx;
  font-weight: 900;
  display: flex;
  align-items: center;
  justify-content: center;
}

// 缩略图
.thumbs {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  margin-top: 23rpx;
}

.thumb {
  width: 154rpx;
  height: 154rpx;
  border-radius: 19rpx;
  margin-right: 19rpx;
  margin-bottom: 19rpx;
  position: relative;
  overflow: hidden;
}

.thumb-img {
  width: 100%;
  height: 100%;
  background-color: $surface-2;
}

.thumb-del {
  position: absolute;
  top: 0;
  right: 0;
  width: 46rpx;
  height: 46rpx;
  background-color: $housing;
  border-bottom-left-radius: 19rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb-del-text {
  color: $ink;
  font-size: 33rpx;
  line-height: 1;
}

.up-title {
  margin-top: 31rpx;
  font-size: 33rpx;
  font-weight: 700;
  color: $ink;
  display: block;
}

.up-sub {
  margin-top: 8rpx;
  font-size: 25rpx;
  line-height: 1.6;
  color: $ink-2;
  display: block;
}

// 主按钮：56px → 108rpx，圆角 16px → 31rpx
.btn-primary {
  width: 100%;
  height: 108rpx;
  margin-top: 31rpx;
  border-radius: 31rpx;
  background-color: $cta;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;

  text {
    font-size: 33rpx;
    font-weight: 900;
    color: $cta-ink;
  }

  &.btn-busy {
    opacity: 0.7;
  }
}

.up-meta {
  margin-top: 23rpx;
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  font-size: 25rpx;
  color: $ink-2;
}

.up-meta-num {
  color: $ink;
  font-weight: 900;
}

// 示例报告卡
.demo {
  margin-top: 23rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 31rpx;
}

.icon-box {
  width: 77rpx;
  height: 77rpx;
  border-radius: 23rpx;
  background-color: $surface-2;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 23rpx;
  flex-shrink: 0;
}

// 眼睛图标（线性，描边 1.8）：用两个椭圆边框近似
.ico-eye {
  width: 42rpx;
  height: 28rpx;
  border: 3rpx solid $ink-2;
  border-radius: 50% / 60%;
  position: relative;

  &::after {
    content: '';
    position: absolute;
    left: 50%;
    top: 50%;
    width: 10rpx;
    height: 10rpx;
    margin-left: -5rpx;
    margin-top: -5rpx;
    border-radius: 50%;
    background-color: $ink-2;
  }
}

.grow {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.demo-t {
  font-size: 29rpx;
  font-weight: 700;
  color: $ink;
}

.demo-s {
  margin-top: 4rpx;
  font-size: 23rpx;
  color: $ink-2;
}

// 右箭头
.chev {
  width: 15rpx;
  height: 15rpx;
  border-top: 3rpx solid $ink-2;
  border-right: 3rpx solid $ink-2;
  transform: rotate(45deg);
  margin-left: 16rpx;
  flex-shrink: 0;
}

// 区块标题 17px → 33rpx
.h2 {
  margin-top: 61rpx;
  margin-bottom: 23rpx;
  font-size: 33rpx;
  font-weight: 800;
  color: $ink;
  display: block;
}

.h2row {
  margin-top: 61rpx;
  margin-bottom: 23rpx;
  display: flex;
  flex-direction: row;
  align-items: baseline;

  .h2 {
    margin: 0;
  }
}

// 信号灯说明卡：底座 $housing
.signal {
  background-color: $housing;
  border: 2rpx solid $line;
  border-radius: 46rpx;
  padding: 42rpx 23rpx 38rpx;
  display: flex;
  flex-direction: row;
}

.signal-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.signal-n {
  margin-top: 27rpx;
  font-size: 29rpx;
  font-weight: 800;
  color: $housing-ink;
}

.signal-d {
  margin-top: 4rpx;
  font-size: 23rpx;
  color: $housing-ink-2;
}

// 列表卡
.list {
  padding: 8rpx 31rpx;
}

.row {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  padding: 27rpx 0;
  border-bottom: 2rpx solid $divider;

  &.row-last {
    border-bottom: none;
  }
}

.row-t {
  font-size: 29rpx;
  font-weight: 700;
  line-height: 1.5;
  color: $ink;
  margin-left: 23rpx;
}

.row-s {
  margin-top: 4rpx;
  margin-left: 23rpx;
  font-size: 23rpx;
  color: $ink-2;
}

.tag {
  flex-shrink: 0;
  font-size: 23rpx;
  font-weight: 700;
  border-radius: 15rpx;
  padding: 6rpx 15rpx;
  margin-left: 16rpx;

  &.tag-red {
    color: $red-text;
    background-color: $red-soft;
  }

  &.tag-amber {
    color: $amber-text;
    background-color: $amber-soft;
  }
}

// 服务说明入口：低调一行，不用卡片
.ai-notice-row {
  margin-top: 46rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
}

.ai-notice-text {
  font-size: 25rpx;
  line-height: 1.6;
  color: $ink-2;
}

.ai-notice-chev {
  width: 12rpx;
  height: 12rpx;
  border-top: 3rpx solid $ink-2;
  border-right: 3rpx solid $ink-2;
  transform: rotate(45deg);
  margin-left: 10rpx;
}

.disclaimer {
  margin-top: 19rpx;
  font-size: 23rpx;
  line-height: 1.6;
  color: $ink-2;
  text-align: center;
}
</style>
