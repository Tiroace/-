<template>
  <view class="lamp" :class="[level, size]" aria-hidden="true"></view>
</template>

<script setup>
// 信号灯：红 / 黄 / 绿 / 灰（截图里没提到）
// 光晕只给灯用，卡片不加阴影（任务书 §5.4）。
defineOptions({ name: 'SignalLamp' });

defineProps({
  level: { type: String, default: 'off' }, // red / amber / green / off
  size: { type: String, default: 'md' }, // sm(10px) / md(16px) / lg(44px)
});
</script>

<style lang="scss" scoped>
.lamp {
  border-radius: 50%;
  flex-shrink: 0;

  // 小圆点 10px 设计稿 → 19rpx，光晕 10px
  &.sm {
    width: 19rpx;
    height: 19rpx;
  }

  // 中号 16px → 31rpx
  &.md {
    width: 31rpx;
    height: 31rpx;
  }

  // 大号 44px → 85rpx，带外圈柔光（设计稿 .lamp 写法）
  &.lg {
    width: 85rpx;
    height: 85rpx;
  }

  &.red {
    background-color: $red;
  }
  &.amber {
    background-color: $amber;
  }
  &.green {
    background-color: $green;
  }
  &.off {
    background-color: $off;
  }

  // 只有亮着的灯发光；灰灯不发光
  &.sm.red {
    box-shadow: 0 0 19rpx $red;
  }
  &.sm.amber {
    box-shadow: 0 0 19rpx $amber;
  }
  &.sm.green {
    box-shadow: 0 0 19rpx $green;
  }

  &.md.red {
    box-shadow: 0 0 24rpx $red;
  }
  &.md.amber {
    box-shadow: 0 0 24rpx $amber;
  }
  &.md.green {
    box-shadow: 0 0 24rpx $green;
  }

  &.lg.red {
    box-shadow: 0 0 0 12rpx $red-soft, 0 0 42rpx $red;
  }
  &.lg.amber {
    box-shadow: 0 0 0 12rpx $amber-soft, 0 0 42rpx $amber;
  }
  &.lg.green {
    box-shadow: 0 0 0 12rpx $green-soft, 0 0 42rpx $green;
  }
}
</style>
