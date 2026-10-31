<template>
  <view class="page">
    <NavBar title="会员" show-back />

    <view class="main">
      <text class="big-title">找工作这段时间，{{ '\n' }}每份邀约都先查一下</text>

      <!-- 价格锚点：真实损失，不编数据（任务书 §7） -->
      <view class="anchor">
        <view class="logo lg">
          <view class="bar"></view>
          <view class="bar"></view>
        </view>
        <text class="anchor-text">少交一次 300 元的押金，{{ '\n' }}会员费就回来了。</text>
      </view>

      <!-- 权益：只写次数和保存时长，不能出现「免广告」 -->
      <view class="card list">
        <view class="perk">
          <view class="icon-box">
            <view class="ico-shield"></view>
          </view>
          <view class="grow">
            <text class="perk-t">每天最多查 20 次</text>
            <text class="perk-s">免费用户：送 3 次，看广告再换</text>
          </view>
        </view>
        <view class="perk perk-last">
          <view class="icon-box">
            <view class="ico-doc"></view>
          </view>
          <view class="grow">
            <text class="perk-t">检查记录保存 30 天</text>
            <text class="perk-s">免费用户保存 7 天</text>
          </view>
        </view>
      </view>

      <text class="h2">选个时长</text>
      <view class="plans">
        <view
          v-for="p in plans"
          :key="p.plan"
          class="plan"
          :class="{ on: selected === p.plan }"
          @tap="selected = p.plan"
        >
          <view class="grow">
            <view class="plan-name-row">
              <text class="plan-name">{{ p.name }}</text>
              <text v-if="p.recommended" class="badge">推荐</text>
            </view>
            <text class="plan-sub">{{ planSub(p) }}</text>
          </view>
          <text class="plan-price">¥{{ fenToYuan(p.amount_fen) }}</text>
        </view>
      </view>
      <text class="meta">一次性购买，到期不自动续费。</text>
    </view>

    <!-- 底部支付栏 -->
    <view class="paybar">
      <view class="btn-primary" :class="{ busy: paying }" @tap="onBuy">
        <text>{{ buyText }}</text>
      </view>
      <text class="pay-tip">开通即表示同意《会员服务协议》</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import NavBar from '@/components/NavBar.vue';
import { fetchMemberPlans, createOrder } from '@/services/api.js';
import { ensureLogin, refreshUser, getUser } from '@/services/session.js';
import { pay as platformPay, currentPlatform } from '@/platform/index.js';
import { canBuyMember } from '@/common/entitlement.js';

defineOptions({ name: 'MemberPage' });

const plans = ref([]);
const selected = ref('month'); // 默认选中月卡（任务书 §6.5）
const paying = ref(false);
const user = ref(getUser());
const canBuy = ref(canBuyMember());

const currentPlan = computed(() => plans.value.find((p) => p.plan === selected.value));
// 按钮文案跟着选择变：「开通月卡 ¥19.9」
const buyText = computed(() => {
  if (paying.value) return '正在下单…';
  const p = currentPlan.value;
  if (!p) return '开通会员';
  return '开通' + p.name + ' ¥' + fenToYuan(p.amount_fen);
});

function fenToYuan(fen) {
  const v = Number(fen || 0) / 100;
  return v.toFixed(2).replace(/0$/, '').replace(/0$/, '');
}

// 每天单价，用于副标题
function planSub(p) {
  if (!p) return '';
  if (p.sub) return p.sub;
  if (p.plan === 'week') return '这周就要面试，选这个';
  const perDay = Number(p.amount_fen) / 100 / Number(p.days || 1);
  if (p.plan === 'quarter') return '约 ¥' + perDay.toFixed(2) + ' 一天，找工作时间长更划算';
  return '约 ¥' + perDay.toFixed(2) + ' 一天';
}

onMounted(() => {
  fetchMemberPlans()
    .then((list) => {
      plans.value = list || [];
      const first = plans.value[0];
      if (first) {
        canBuy.value = canBuy.value && first.available_on_android !== false;
      }
      // 默认选中月卡；没有月卡就选第一个
      const has = plans.value.some((p) => p.plan === 'month');
      selected.value = has ? 'month' : (plans.value[0] && plans.value[0].plan) || 'month';
    })
    .catch(() => {
      plans.value = [];
    });
  ensureLogin()
    .then(() => refreshUser())
    .then((u) => {
      user.value = u;
    })
    .catch(() => {});
});
void user;

function onBuy() {
  if (paying.value) return;
  if (!canBuy.value) {
    // iOS 不支持虚拟支付：所有会员入口都隐藏，这里理论上看不到
    uni.showToast({ title: '当前环境暂不支持购买', icon: 'none' });
    return;
  }
  paying.value = true;
  ensureLogin()
    .then(() => createOrder(selected.value, currentPlatform.platform === 'weixin' ? 'weixin' : 'toutiao'))
    .then((order) =>
      platformPay(order.pay_params).then((res) => {
        if (!res.ok) throw new Error(res.reason === 'unsupported' ? '当前环境暂不支持支付' : '支付未完成');
        return order;
      })
    )
    .then(() => refreshUser())
    .then((u) => {
      user.value = u;
      paying.value = false;
      uni.showModal({
        title: '会员已开通',
        content: '现在每天最多可以查 20 次。',
        showCancel: false,
        success: () => {
          // 返回来源页（任务书 §6.5）
          uni.navigateBack({ fail: () => uni.switchTab({ url: '/pages/index/index' }) });
        },
      });
    })
    .catch((err) => {
      paying.value = false;
      uni.showToast({ title: (err && err.message) || '下单失败', icon: 'none' });
    });
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background-color: $bg;
  padding-bottom: calc(240rpx + env(safe-area-inset-bottom));
}

.main {
  padding: 31rpx 39rpx 0;
  display: flex;
  flex-direction: column;
}

// 页面标题 26px → 50rpx，900
.big-title {
  font-size: 50rpx;
  font-weight: 900;
  line-height: 1.32;
  color: $ink;
  white-space: pre-line;
}

.anchor {
  margin-top: 46rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
}

.logo {
  width: 88rpx;
  height: 88rpx;
  border-radius: 27rpx;
  background-color: $cta;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  margin-right: 27rpx;
  flex-shrink: 0;
}

.bar {
  width: 11rpx;
  height: 38rpx;
  border-radius: 6rpx;
  background-color: $cta-ink;

  & + & {
    margin-left: 11rpx;
  }
}

.anchor-text {
  flex: 1;
  font-size: 29rpx;
  line-height: 1.6;
  color: $ink-3;
  white-space: pre-line;
}

.card {
  background-color: $surface;
  border-radius: 38rpx;
}

.list {
  margin-top: 38rpx;
  padding: 8rpx 31rpx;
}

.perk {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 27rpx 0;
  border-bottom: 2rpx solid $divider;

  &.perk-last {
    border-bottom: none;
  }
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

.ico-shield {
  width: 30rpx;
  height: 34rpx;
  border: 3rpx solid $ink-3;
  border-radius: 8rpx 8rpx 15rpx 15rpx;
}

.ico-doc {
  width: 26rpx;
  height: 32rpx;
  border: 3rpx solid $ink-3;
  border-radius: 5rpx;
}

.grow {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.perk-t {
  font-size: 29rpx;
  font-weight: 700;
  color: $ink;
}

.perk-s {
  margin-top: 4rpx;
  font-size: 23rpx;
  color: $ink-2;
}

.h2 {
  margin-top: 46rpx;
  margin-bottom: 23rpx;
  font-size: 33rpx;
  font-weight: 800;
  color: $ink;
  display: block;
}

.plans {
  display: flex;
  flex-direction: column;
}

.plan {
  background-color: $surface;
  border: 3rpx solid $line;
  border-radius: 31rpx;
  padding: 27rpx 31rpx;
  margin-bottom: 23rpx;
  display: flex;
  flex-direction: row;
  align-items: center;

  &.on {
    border-color: $cta;
    background-color: $brand-soft;
  }
}

.plan-name-row {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.plan-name {
  font-size: 29rpx;
  font-weight: 700;
  color: $ink;
}

.badge {
  margin-left: 15rpx;
  font-size: 21rpx;
  font-weight: 700;
  color: $cta-ink;
  background-color: $cta;
  border-radius: 8rpx;
  padding: 2rpx 12rpx;
}

.plan-sub {
  margin-top: 6rpx;
  font-size: 23rpx;
  color: $ink-2;
}

.plan-price {
  font-size: 38rpx;
  font-weight: 900;
  color: $ink;
  margin-left: 23rpx;
}

.meta {
  margin-top: 8rpx;
  font-size: 23rpx;
  color: $ink-2;
  display: block;
}

// 底部支付栏
.paybar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: $surface;
  border-top: 2rpx solid $line;
  padding: 23rpx 39rpx calc(23rpx + env(safe-area-inset-bottom));
}

.btn-primary {
  width: 100%;
  height: 108rpx;
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

  &.busy {
    opacity: 0.7;
  }
}

.pay-tip {
  margin-top: 15rpx;
  font-size: 21rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}
</style>
