<template>
  <view class="page">
    <NavBar title="我的" />

    <view class="main">
      <!-- 头像 + 昵称 + 免费/会员标识 -->
      <view class="profile">
        <view class="avatar">
          <view class="avatar-bar"></view>
          <view class="avatar-bar"></view>
        </view>
        <view class="profile-info">
          <text class="name">{{ displayName }}</text>
          <view class="chip-row">
            <text class="chip">{{ memberActive ? '会员' : '免费用户' }}</text>
          </view>
        </view>
      </view>

      <!-- 三个统计 -->
      <view class="card stats">
        <view class="stat">
          <text class="stat-num">{{ isUnlimited ? '不限' : balance }}</text>
          <text class="stat-label">剩余次数</text>
        </view>
        <view class="stat">
          <text class="stat-num">{{ checkedCount }}</text>
          <text class="stat-label">查过的工作</text>
        </view>
        <view class="stat">
          <text class="stat-num">{{ redCount }}</text>
          <text class="stat-label">亮过的红灯</text>
        </view>
      </view>

      <!-- 会员条（D39：会员关闭时不渲染，整个条不出现） -->
      <view v-if="membershipVisible" class="vip-strip" @tap="gotoMember">
        <view class="star"></view>
        <text class="vip-text">{{ vipStripText }}</text>
        <text class="vip-go">看看</text>
      </view>

      <!-- 检查记录 -->
      <view class="h2row">
        <text class="h2">检查记录</text>
        <!-- D39：会员关闭时不再显示 30 天，统一 7 天 -->
        <text class="h2-side">保留 {{ memberActive && membershipVisible ? 30 : 7 }} 天</text>
      </view>

      <view v-if="!reports.length" class="card empty">
        <view class="icon-box">
          <view class="ico-doc"></view>
        </view>
        <text class="empty-t">还没有检查记录</text>
        <text class="empty-s">下次收到面试邀约，先截图发过来。</text>
        <view class="btn-small" @tap="gotoIndex"><text>去检查</text></view>
      </view>

      <view v-else class="card record-list">
        <view
          v-for="(r, idx) in reports"
          :key="r.report_id"
          class="record"
          :class="{ 'record-last': idx === reports.length - 1 }"
          @tap="openReport(r)"
        >
          <SignalLamp :level="overallToLamp(r.risk_level)" size="sm" />
          <view class="grow">
            <text class="record-summary">{{ r.summary }}</text>
            <text class="record-date">{{ r.created_at }}</text>
          </view>
          <view class="chev"></view>
        </view>
      </view>

      <!-- 菜单：只留 4 项 -->
      <view class="card menu">
        <view class="menu-item" @tap="gotoDoc('feedback')">
          <text class="menu-text">意见反馈与申诉</text>
          <view class="chev"></view>
        </view>
        <view class="menu-item" @tap="gotoDoc('ai')">
          <text class="menu-text">检查规则说明</text>
          <view class="chev"></view>
        </view>
        <view class="menu-item" @tap="gotoDoc('privacy')">
          <text class="menu-text">隐私政策</text>
          <view class="chev"></view>
        </view>
        <view class="menu-item menu-last" @tap="gotoDoc('agreement')">
          <text class="menu-text">用户协议</text>
          <view class="chev"></view>
        </view>
      </view>

      <!-- 开发自测入口：用编译期条件编译，正式构建时整段不参与编译
           （v-if 只隐藏渲染、文案仍会进包，所以必须用 #ifdef） -->
      <!-- #ifdef MP-DEV -->
      <view class="card dev-entry" @tap="gotoDev">
        <text class="dev-text">开发自测</text>
      </view>
      <!-- #endif -->

      <text class="ver">{{ appName }} {{ appVersion }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import NavBar from '@/components/NavBar.vue';
import SignalLamp from '@/components/SignalLamp.vue';
import { ensureLogin, refreshUser, getUser } from '@/services/session.js';
import { fetchReports } from '@/services/api.js';
import { APP_NAME, APP_VERSION } from '@/common/brand.js';
import { isMembershipVisible } from '@/common/entitlement.js';
import { isUnlimitedEnv } from '@/common/env.js';
import { detectPlatform, PLATFORM_LABELS } from '@/platform/detect.js';

defineOptions({ name: 'MinePage' });

const user = ref(null);
const reports = ref([]);
const appName = APP_NAME;
const appVersion = APP_VERSION;

// 开发自测入口用编译期条件编译（模板里的 #ifdef MP-DEV），不再靠运行期判断

const balance = computed(() => Number((user.value && user.value.quota && user.value.quota.balance) || 0));
// 开发版/体验版不限次数（老板 2026-11-04 定）
const isUnlimited = isUnlimitedEnv();
const memberActive = computed(() => !!(user.value && user.value.membership && user.value.membership.active));
// D39：会员关闭时整条会员入口不渲染，也不再提示「开通会员每天 20 次」
const membershipVisible = isMembershipVisible();
// /me 新增的两个统计字段（后端会给），没有时显示 0
const checkedCount = computed(() => Number((user.value && user.value.checked_count) || 0));
const redCount = computed(() => Number((user.value && user.value.red_count) || 0));

const displayName = computed(() => {
  const u = user.value;
  if (!u) return '未登录';
  // 拿不到平台昵称时按**当前运行平台**给兜底文案，不能写死「抖音用户」——
  // 微信版里显示「抖音用户」是明显错误。平台取自 detectPlatform()。
  const fallback = PLATFORM_LABELS[detectPlatform().platform] || '用户';
  return u.nickname || u.nick_name || fallback;
});

const vipStripText = computed(() => {
  const u = user.value;
  if (u && u.membership && u.membership.active && u.membership.expires_at) {
    return '会员有效期至 ' + formatExpire(u.membership.expires_at);
  }
  return '开通会员，每天最多查 20 次';
});

function formatExpire(s) {
  // 契约里的格式是 YYYY-MM-DD HH:MM:SS，这里只显示 M 月 D 日
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return s;
  return Number(m[2]) + ' 月 ' + Number(m[3]) + ' 日';
}

// 旧契约的 risk_level → 新灯色
function overallToLamp(level) {
  const map = { high: 'red', warn: 'amber', notice: 'amber', safe: 'green' };
  return map[level] || 'off';
}

function loadReports() {
  return fetchReports({ limit: 20 })
    .then((res) => {
      reports.value = (res && res.items) || [];
    })
    .catch(() => {
      reports.value = [];
    });
}

function load() {
  ensureLogin()
    .then((u) => {
      user.value = u;
      return refreshUser();
    })
    .then((u) => {
      user.value = u;
      return loadReports();
    })
    .catch(() => {
      user.value = null;
    });
}

onMounted(load);
onShow(() => {
  if (getUser()) {
    refreshUser()
      .then((u) => {
        user.value = u;
        return loadReports();
      })
      .catch(() => {});
  }
});

function openReport(r) {
  const q = r.task_id ? 'task_id=' + r.task_id : 'report_id=' + r.report_id;
  uni.navigateTo({ url: '/pages/report/index?' + q });
}

function gotoMember() {
  // D39：会员关闭时不跳转（条本身也不渲染，这里兜底）
  if (!isMembershipVisible()) return;
  uni.navigateTo({ url: '/pages/member/index' });
}

function gotoIndex() {
  uni.switchTab({ url: '/pages/index/index' });
}

function gotoDoc(type) {
  uni.navigateTo({ url: '/pages/doc/index?type=' + type });
}

function gotoDev() {
  uni.navigateTo({ url: '/pages/dev/index' });
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background-color: $bg;
}

// 关键：底部留出原生 tabBar 高度 + 安全区，否则最后一行被挡（任务书 §3 bug 修复）
.main {
  padding: 0 39rpx;
  padding-bottom: calc(24rpx + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
}

.profile {
  margin-top: 39rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
}

// 头像：品牌黄方块 + 暂停键
.avatar {
  width: 100rpx;
  height: 100rpx;
  border-radius: 31rpx;
  background-color: $cta;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  margin-right: 23rpx;
}

.avatar-bar {
  width: 11rpx;
  height: 38rpx;
  border-radius: 6rpx;
  background-color: $cta-ink;

  & + & {
    margin-left: 11rpx;
  }
}

.profile-info {
  display: flex;
  flex-direction: column;
}

.name {
  font-size: 35rpx;
  font-weight: 900;
  color: $ink;
}

.chip-row {
  margin-top: 10rpx;
  display: flex;
  flex-direction: row;
}

.chip {
  font-size: 23rpx;
  color: $ink-2;
  background-color: $surface-2;
  border-radius: 15rpx;
  padding: 4rpx 15rpx;
}

.card {
  background-color: $surface;
  border-radius: 38rpx;
}

.stats {
  margin-top: 38rpx;
  display: flex;
  flex-direction: row;
  padding: 31rpx 0;
}

.stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-num {
  font-size: 50rpx;
  font-weight: 900;
  color: $ink;
}

.stat-label {
  margin-top: 8rpx;
  font-size: 23rpx;
  color: $ink-2;
}

// 会员条
.vip-strip {
  margin-top: 23rpx;
  background-color: $brand-soft;
  border: 2rpx solid $brand-line;
  border-radius: 31rpx;
  padding: 27rpx 31rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
}

.star {
  width: 26rpx;
  height: 26rpx;
  background-color: $cta;
  transform: rotate(45deg);
  border-radius: 5rpx;
  margin-right: 23rpx;
  flex-shrink: 0;
}

.vip-text {
  flex: 1;
  font-size: 27rpx;
  font-weight: 700;
  color: $brand-text;
}

.vip-go {
  font-size: 25rpx;
  font-weight: 700;
  color: $cta;
}

// 区块标题行
.h2row {
  margin-top: 54rpx;
  margin-bottom: 23rpx;
  display: flex;
  flex-direction: row;
  align-items: baseline;
  justify-content: space-between;
}

.h2 {
  font-size: 33rpx;
  font-weight: 800;
  color: $ink;
}

.h2-side {
  font-size: 25rpx;
  color: $ink-2;
}

// 空状态
.empty {
  padding: 50rpx 31rpx 42rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.icon-box {
  width: 92rpx;
  height: 92rpx;
  border-radius: 27rpx;
  background-color: $surface-2;
  display: flex;
  align-items: center;
  justify-content: center;
}

// 文档图标
.ico-doc {
  width: 34rpx;
  height: 42rpx;
  border: 3rpx solid $ink-2;
  border-radius: 6rpx;
  position: relative;

  &::after {
    content: '';
    position: absolute;
    left: 6rpx;
    right: 6rpx;
    top: 12rpx;
    height: 3rpx;
    background-color: $ink-2;
  }
}

.empty-t {
  margin-top: 23rpx;
  font-size: 29rpx;
  font-weight: 700;
  color: $ink;
}

.empty-s {
  margin-top: 8rpx;
  font-size: 25rpx;
  color: $ink-2;
}

.btn-small {
  margin-top: 31rpx;
  height: 85rpx;
  padding: 0 39rpx;
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

// 记录列表
.record-list {
  padding: 8rpx 31rpx;
}

.record {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 27rpx 0;
  border-bottom: 2rpx solid $divider;

  &.record-last {
    border-bottom: none;
  }
}

.grow {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  margin-left: 23rpx;
}

.record-summary {
  font-size: 29rpx;
  color: $ink;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.record-date {
  margin-top: 6rpx;
  font-size: 23rpx;
  color: $ink-2;
}

.chev {
  width: 15rpx;
  height: 15rpx;
  border-top: 3rpx solid $ink-2;
  border-right: 3rpx solid $ink-2;
  transform: rotate(45deg);
  margin-left: 16rpx;
  flex-shrink: 0;
}

// 菜单
.menu {
  margin-top: 39rpx;
  padding: 0 31rpx;
}

.menu-item {
  height: 100rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  border-bottom: 2rpx solid $divider;

  &.menu-last {
    border-bottom: none;
  }
}

.menu-text {
  font-size: 29rpx;
  color: $ink;
}

.dev-entry {
  margin-top: 23rpx;
  padding: 31rpx;
  background-color: $surface-2;
}

.dev-text {
  font-size: 27rpx;
  color: $ink-2;
}

.ver {
  margin-top: 39rpx;
  margin-bottom: 19rpx;
  font-size: 23rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}
</style>
