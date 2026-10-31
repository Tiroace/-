<template>
  <view class="brand-row">
    <view class="logo" :class="sizeClass" aria-hidden="true">
      <view class="bar"></view>
      <view class="bar"></view>
    </view>
    <text v-if="showName" class="brand-name">{{ appName }}</text>
  </view>
</template>

<script setup>
// 品牌标识：黄色圆角方块 + 两根深色竖条（暂停键），代表「等等」
import { APP_NAME } from '@/common/brand.js';

defineOptions({ name: 'BrandMark' });

defineProps({
  showName: { type: Boolean, default: true },
  size: { type: String, default: 'md' }, // sm / md / lg
});
const appName = APP_NAME;
</script>

<style lang="scss" scoped>
.brand-row {
  display: flex;
  flex-direction: row;
  align-items: center;
}

// 32px 设计稿 → 61rpx
.logo {
  width: 61rpx;
  height: 61rpx;
  border-radius: 19rpx;
  background-color: $cta;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  margin-right: 19rpx;
  flex-shrink: 0;

  &.sm {
    width: 46rpx;
    height: 46rpx;
    border-radius: 14rpx;
    margin-right: 14rpx;
  }

  &.lg {
    width: 88rpx;
    height: 88rpx;
    border-radius: 27rpx;
    margin-right: 0;
  }
}

// 竖条 4×14 设计稿 → 8rpx×27rpx
.bar {
  width: 8rpx;
  height: 27rpx;
  border-radius: 4rpx;
  background-color: $cta-ink;

  &.sm,
  .logo.sm & {
    width: 6rpx;
    height: 20rpx;
  }

  .logo.lg & {
    width: 11rpx;
    height: 38rpx;
  }

  & + & {
    margin-left: 8rpx;
  }
}

.brand-name {
  font-size: 33rpx;
  font-weight: 900;
  color: $ink;
  letter-spacing: 1rpx;
}
</style>
