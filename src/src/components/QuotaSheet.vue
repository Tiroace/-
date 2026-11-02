<template>
  <view v-if="visible" class="sheet-root">
    <!-- 背景压暗 -->
    <view class="dim" @tap="onClose"></view>

    <view class="sheet">
      <view class="handle"></view>
      <text class="sheet-title">免费次数用完了</text>
      <text class="lead">选一种方式，继续检查。</text>

      <!-- 看广告：只在今天还有次数时显示 -->
      <view v-if="remainingAd > 0" class="opt">
        <view class="icon-44">
          <view class="ico-play"></view>
        </view>
        <view class="grow">
          <text class="opt-t">看一段广告，再查 1 次</text>
          <text class="opt-s">{{ adLoading ? '广告加载中…' : '看完就到账，今天还能看 ' + remainingAd + ' 次' }}</text>
        </view>
        <view class="btn-small" :class="{ busy: adLoading }" @tap="onWatchAd">
          <text>{{ adLoading ? '加载中' : '看广告' }}</text>
        </view>
      </view>
      <view v-else class="opt">
        <view class="icon-44">
          <view class="ico-play ico-off"></view>
        </view>
        <view class="grow">
          <text class="opt-t">今天看广告的次数用完了</text>
          <text class="opt-s">明天再来，次数每天刷新</text>
        </view>
      </view>

      <!-- 会员卡
           【D39】个人主体不能开微信虚拟支付 → 纯免费 + 流量主广告。
           这里是编译期条件编译，不是 v-if：v-if 只影响渲染，文案照样进包，
           审核能看到「开通会员 / 周卡 ¥」这类字样，等于把未开放功能带上了架。
           所以用 #ifdef QBL_MEMBER_ON 包住，提审包里这段 wxml 根本不存在。
           将来主体变更成企业、支付能开了：定义 QBL_MEMBER_ON 并重新提审即可。 -->
      <!-- #ifdef QBL_MEMBER_ON -->
      <view v-if="memberAvailable" class="vip">
        <view class="vip-head">
          <view class="icon-44 gold">
            <view class="ico-star"></view>
          </view>
          <view class="grow">
            <text class="vip-t">开通会员，找工作期间放心查</text>
            <text class="vip-s">每天最多查 20 次<text v-if="weeklyPrice">，周卡 ¥{{ weeklyPrice }} 起</text></text>
          </view>
        </view>
        <view class="btn-primary" @tap="onOpenMember"><text>看看会员</text></view>
      </view>

      <text v-if="memberAvailable" class="note">会员是一次性购买，不会自动续费。</text>
      <!-- #endif -->
    </view>
  </view>
</template>

<script setup>
// 次数用完弹窗（设计稿 03）
// §6.2：用户点了「看广告」才走广告流程；/ad/reward 对 no_fill 也发次数。
// iOS 不可付费时：会员卡整块隐藏，弹窗里不出现价格与付费字眼。
defineOptions({ name: 'QuotaSheet' });

const props = defineProps({
  visible: { type: Boolean, default: false },
  remainingAd: { type: Number, default: 5 },
  adCap: { type: Number, default: 5 },
  memberAvailable: { type: Boolean, default: false },
  weeklyPrice: { type: String, default: '' },
  adLoading: { type: Boolean, default: false },
});

const emit = defineEmits(['close', 'watch-ad', 'open-member']);

function onClose() {
  emit('close');
}

function onWatchAd() {
  if (props.adLoading) return;
  emit('watch-ad');
}

function onOpenMember() {
  emit('open-member');
}
</script>

<style lang="scss" scoped>
.sheet-root {
  position: fixed;
  left: 0;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 99;
}

.dim {
  position: absolute;
  left: 0;
  top: 0;
  right: 0;
  bottom: 0;
  // 压暗层：用底座色 + 透明度（不用纯黑，和深色体系一致）
  background-color: $housing;
  opacity: 0.82;
}

// 底部弹出
.sheet {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: $surface;
  border-radius: 46rpx 46rpx 0 0;
  padding: 19rpx 39rpx calc(38rpx + env(safe-area-inset-bottom));
}

.handle {
  width: 77rpx;
  height: 8rpx;
  border-radius: 4rpx;
  background-color: $line;
  margin: 0 auto 31rpx;
}

// 弹窗标题 22px → 42rpx，900
.sheet-title {
  font-size: 42rpx;
  font-weight: 900;
  color: $ink;
  text-align: center;
  display: block;
}

.lead {
  margin-top: 12rpx;
  font-size: 27rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}

.opt {
  margin-top: 42rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
}

.icon-44 {
  width: 85rpx;
  height: 85rpx;
  border-radius: 27rpx;
  background-color: $surface-2;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 23rpx;
  flex-shrink: 0;

  &.gold {
    background-color: $brand-soft;
  }
}

// 播放三角
.ico-play {
  width: 0;
  height: 0;
  border-top: 12rpx solid transparent;
  border-bottom: 12rpx solid transparent;
  border-left: 19rpx solid $ink;
  margin-left: 6rpx;

  &.ico-off {
    border-left-color: $off-text;
  }
}

// 星星：用一个旋转的方块 + 四条短线近似
.ico-star {
  width: 26rpx;
  height: 26rpx;
  background-color: $cta;
  transform: rotate(45deg);
  border-radius: 5rpx;
}

.grow {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.opt-t {
  font-size: 29rpx;
  font-weight: 700;
  color: $ink;
}

.opt-s {
  margin-top: 4rpx;
  font-size: 23rpx;
  color: $ink-2;
}

// 小按钮 44 高 → 85rpx
.btn-small {
  height: 85rpx;
  padding: 0 31rpx;
  border-radius: 27rpx;
  border: 3rpx solid $outline;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 16rpx;

  text {
    font-size: 29rpx;
    font-weight: 700;
    color: $ink;
  }

  &.busy {
    opacity: 0.6;
  }
}

.vip {
  margin-top: 38rpx;
  background-color: $surface-2;
  border-radius: 31rpx;
  padding: 31rpx;
}

.vip-head {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.vip-t {
  font-size: 29rpx;
  font-weight: 700;
  color: $ink;
}

.vip-s {
  margin-top: 4rpx;
  font-size: 23rpx;
  color: $ink-2;
}

.btn-primary {
  width: 100%;
  height: 100rpx;
  margin-top: 27rpx;
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

.note {
  margin-top: 27rpx;
  font-size: 23rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}
</style>
