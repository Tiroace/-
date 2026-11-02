<template>
  <view class="page">
    <!-- 自定义导航栏：品牌名只在这里出现一次（任务书 §3 bug 修复） -->
    <NavBar brand />

    <view class="main">
      <text class="hero-title">去面试之前，{{ '\n' }}先让我看一眼</text>
      <text class="hero-sub">招聘截图发过来，30 秒告诉你这份工作有没有坑。</text>

      <!-- 上传卡 -->
      <view class="card upload">
        <!-- 插画：三张截图，中间一张标出可疑行 -->
        <view class="illus" aria-hidden="true">
          <view class="shot l"></view>
          <view class="shot r"></view>
          <view class="shot m">
            <view class="bar-line" style="width: 70%"></view>
            <view class="bar-line" style="width: 90%"></view>
            <view class="bar-line hit" style="width: 100%"></view>
            <view class="bar-line" style="width: 55%"></view>
            <view class="bar-line" style="width: 80%"></view>
          </view>
          <view class="bang">!</view>
        </view>

        <!-- 已选截图缩略图（可删除） -->
        <view v-if="images.length" class="thumbs">
          <view v-for="(img, idx) in images" :key="img.path" class="thumb">
            <image class="thumb-img" :src="img.path" mode="aspectFill" />
            <view class="thumb-del" @tap="removeImage(idx)">
              <text class="thumb-del-text">×</text>
            </view>
          </view>
        </view>

        <text class="up-title">把招聘截图发给我</text>
        <text class="up-sub">岗位详情、HR 聊天记录都行，一次最多 3 张。</text>

        <view class="btn-primary" :class="{ 'btn-busy': submitting }" @tap="onPickOrStart">
          <text>{{ buttonText }}</text>
        </view>

        <view class="up-meta">
          <text>还能免费查 <text class="up-meta-num">{{ balance }}</text> 次</text>
          <text>没查出结果，不扣次数</text>
        </view>
      </view>

      <!-- 示例报告入口：内置数据，不扣次数 -->
      <view class="card demo" @tap="openSampleReport">
        <view class="icon-box">
          <view class="ico-eye"></view>
        </view>
        <view class="grow">
          <text class="demo-t">没有截图？先看一份示例报告</text>
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
        <text class="ai-notice-text">本服务根据截图文字和规则库自动检查，查看检查规则说明</text>
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
import { ensureLogin, getUser, refreshUser } from '@/services/session.js';
import { createAnalysis, uploadImage, claimAdReward, newRequestId, ApiError } from '@/services/api.js';
import { runRewardedFlow, canTriggerAd } from '@/common/adGuard.js';
import { canBuyMember, isMembershipVisible } from '@/common/entitlement.js';
import { getAdUnitId } from '@/common/config.js';
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
const submitting = ref(false);
const balance = ref(0);
const adRemaining = ref(5);
const adCap = ref(5);
const adLoading = ref(false);
const showQuota = ref(false);
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
  if (submitting.value) return '正在提交…';
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
}

onMounted(() => {
  ensureLogin()
    .then((u) => {
      syncUser(u);
      return refreshUser();
    })
    .then(syncUser)
    .catch(() => {});
});

onShow(() => {
  if (getUser()) refreshUser().then(syncUser).catch(() => {});
});

// 主按钮：没选图先选图，选了图就开始检查
function onPickOrStart() {
  if (submitting.value) return;
  if (!images.value.length) {
    chooseImages();
    return;
  }
  if (balance.value <= 0) {
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
  ensureLogin()
    .then(() => uploadAll(images.value.map((i) => i.path)))
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
    showQuota.value = true;
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
function onWatchAd() {
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
