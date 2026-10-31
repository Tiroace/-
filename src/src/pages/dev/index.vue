<template>
  <view class="page">
    <view class="card">
      <text class="title">开发自测（内部页面，提审前删除）</text>
      <text class="text-muted self-tip"
        >用于在开发者工具里验证 §6.2 广告规范、兜底逻辑和合规文案。切换后重新点击即生效。</text
      >

      <view class="item">
        <view class="col item-text">
          <text class="item-title">使用真后端（不走 mock）</text>
          <text class="text-muted text-small"
            >当前：{{ useReal ? '真后端 → ' + apiBase : '本地 mock' }}。切换后重进页面生效</text
          >
        </view>
        <switch :checked="useReal" :color="SWITCH_COLOR" @change="toggleReal" />
      </view>

      <view class="item">
        <view class="col item-text">
          <text class="item-title">强制 Mock 平台（无真实广告位时用）</text>
          <text class="text-muted text-small">当前：{{ forceMock ? '已开启' : '已关闭' }}</text>
        </view>
        <switch :checked="forceMock" :color="SWITCH_COLOR" @change="toggleForceMock" />
      </view>

      <view class="item">
        <view class="col item-text">
          <text class="item-title">模拟「广告拉不出来」</text>
          <text class="text-muted text-small">当前：{{ mockAdFail ? '会走兜底' : '不会' }}</text>
        </view>
        <switch :checked="mockAdFail" :color="SWITCH_COLOR" @change="toggleMockAdFail" />
      </view>
    </view>

    <view class="card">
      <text class="title">联调自检（真后端模式才有用）</text>
      <text class="text-muted self-tip"
        >真后端要先起在本机：python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000</text
      >
      <view v-for="(r, i) in probeResults" :key="i" class="check-item">
        <text class="check-icon" :class="r.pass ? 'pass' : 'fail'"><view class="check-dot" :class="r.pass ? 'pass' : 'fail'"></view></text>
        <text class="check-text">{{ r.name }}</text>
      </view>
      <view class="btn-gray run-btn" @tap="runProbe"><text>探测后端</text></view>
    </view>

    <view class="card">
      <text class="title">自检结果</text>
      <view v-for="(c, i) in checks" :key="i" class="check-item">
        <text class="check-icon" :class="c.pass ? 'pass' : 'fail'"><view class="check-dot" :class="c.pass ? 'pass' : 'fail'"></view></text>
        <text class="check-text">{{ c.name }}</text>
      </view>
      <view class="btn-gray run-btn" @tap="runChecks"><text>重新自检</text></view>
    </view>

    <view class="card">
      <text class="title">平台信息</text>
      <text class="info-line">平台：{{ platformInfo.platform }}</text>
      <text class="info-line">广告位 ID：{{ platformInfo.adUnitId || '（未配置，走兜底）' }}</text>
      <text class="info-line">激励视频可用：{{ platformInfo.adSupported ? '是' : '否' }}</text>
      <text class="info-line">会员可购买：{{ platformInfo.canBuy ? '是' : '否' }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { currentPlatform, isRewardedAdSupported, isPaymentSupported } from '@/platform/index.js';
import {
  getAdUnitId,
  useMock,
  getApiBaseUrl,
  STORAGE_KEYS,
} from '@/common/config.js';
import { canTriggerAd, getRemainingTriggers } from '@/common/adGuard.js';
import { canBuyMember } from '@/common/entitlement.js';
import { DISCLAIMER_TEXT, FORBIDDEN_WORDS } from '@/common/constants.js';
import { maskAll, maskCompanyName, maskPersonName } from '@/common/format.js';
import { SWITCH_COLOR } from '@/common/brand.js';

defineOptions({ name: 'DevPage' });

const forceMock = ref(false);
const mockAdFail = ref(false);
const useReal = ref(false);
const apiBase = ref('');
const checks = ref([]);
const probeResults = ref([]);
const platformInfo = ref({});

onMounted(() => {
  forceMock.value = uni.getStorageSync(STORAGE_KEYS.forceMock) === '1';
  mockAdFail.value = uni.getStorageSync(STORAGE_KEYS.mockAdFail) === '1';
  useReal.value = !useMock();
  apiBase.value = getApiBaseUrl();
  platformInfo.value = {
    platform: currentPlatform.platform,
    adUnitId: getAdUnitId(),
    adSupported: isRewardedAdSupported(),
    canBuy: canBuyMember(),
    paySupported: isPaymentSupported(),
  };
  runChecks();
});

// 真后端 / mock 切换：写本地存储，重进页面生效（不重新编译）
function toggleReal(e) {
  uni.setStorageSync(STORAGE_KEYS.useRealBackend, e.detail.value ? '1' : '0');
  useReal.value = e.detail.value;
  uni.showToast({ title: '切换成功，请重进页面', icon: 'none' });
}

// 探测后端：真后端模式下逐项打接口，打印状态
function runProbe() {
  probeResults.value = [];
  if (useMock()) {
    probeResults.value = [{ name: '当前是 mock 模式，先打开「使用真后端」', pass: false }];
    return;
  }
  const base = getApiBaseUrl();
  const add = (name, pass) => probeResults.value.push({ name, pass });

  uni.request({
    url: base + '/health',
    timeout: 5000,
    success: (res) => {
      add('GET /health → ' + res.statusCode, res.statusCode === 200);
    },
    fail: (err) => {
      add('连不上 ' + base + '（' + ((err && err.errMsg) || '网络错误') + '）', false);
    },
    complete: () => {
      // 登录探测
      uni.request({
        url: base + '/auth/login',
        method: 'POST',
        timeout: 8000,
        header: { 'content-type': 'application/json' },
        data: { code: 'mock', platform: 'toutiao' },
        success: (res) => {
          const body = res.data || {};
          if (body.ok === true) {
            add(
              'POST /auth/login → 余额 ' +
                ((body.data.quota && body.data.quota.balance) || '?') +
                '，platform_mode=' +
                (body.data.platform_mode || '?'),
              true
            );
          } else {
            add('POST /auth/login 失败：' + ((body.error && body.error.code) || res.statusCode), false);
          }
        },
        fail: () => add('POST /auth/login 网络失败', false),
      });
    },
  });
}

function toggleForceMock(e) {
  uni.setStorageSync(STORAGE_KEYS.forceMock, e.detail.value ? '1' : '0');
  forceMock.value = e.detail.value;
}

function toggleMockAdFail(e) {
  uni.setStorageSync(STORAGE_KEYS.mockAdFail, e.detail.value ? '1' : '0');
  mockAdFail.value = e.detail.value;
}

function runChecks() {
  const result = [];

  // 1. 免责声明文案完整（D20 定稿：必须带后半句，且不含 AI 字样）
  const need =
    '本报告由系统根据截图文字和规则库自动生成，仅供参考，不构成法律意见，也不代表对任何企业的评价；截图不完整或内容不实都会影响判断，重要事项请自行核实。';
  result.push({ name: '免责声明 = D20 定稿原文', pass: DISCLAIMER_TEXT === need });
  result.push({
    name: '免责声明不含 AI 字样',
    pass: !/(?<![A-Za-z])AI(?![A-Za-z])/.test(DISCLAIMER_TEXT),
  });

  // 2. 禁用词清单存在
  result.push({ name: '禁用词清单已加载（' + FORBIDDEN_WORDS.length + ' 个）', pass: FORBIDDEN_WORDS.length >= 4 });

  // 3. 分享脱敏
  const masked = maskAll('联系张经理 13812345678 微信 wxid_abc123');
  result.push({ name: '手机号脱敏', pass: masked.indexOf('13812345678') === -1 });

  // 4. 公司名/姓名打码
  const mComp = maskCompanyName('某某网络科技有限公司');
  const mName = maskPersonName('张伟');
  result.push({
    name: '公司名/姓名打码',
    pass: mComp !== '某某网络科技有限公司' && mName !== '张伟',
  });

  // 5. 60 秒频率限制可用
  result.push({
    name: '60 秒内最多 5 次调起（当前剩余 ' + getRemainingTriggers('dev') + ' 次）',
    pass: canTriggerAd('dev'),
  });

  checks.value = result;
}
</script>

<style scoped>
.self-tip {
  display: block;
  margin: 12rpx 0 12rpx;
}

.item {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 0;
  border-bottom: 2rpx solid $surface-2;
}

.item:last-child {
  border-bottom: none;
}

.item-text {
  flex: 1;
}

.item-title {
  font-size: 28rpx;
}

.check-item {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 14rpx 0;
}

.check-dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  margin-right: 16rpx;
  flex-shrink: 0;
}

.check-dot.pass {
  background-color: $green;
}

.check-dot.fail {
  background-color: $red;
}

.check-text {
  flex: 1;
  font-size: 26rpx;
  color: $ink-3;
}

.run-btn {
  margin-top: 20rpx;
}

.info-line {
  display: block;
  font-size: 26rpx;
  color: $ink-3;
  margin-top: 12rpx;
}
</style>
