<template>
  <view class="nav-wrap" :style="{ paddingTop: statusBarHeight + 'px' }">
    <view class="nav-bar" :style="{ height: navHeight + 'px' }">
      <view v-if="showBack" class="nav-back" @tap="goBack">
        <view class="back-icon"></view>
      </view>
      <view class="nav-left">
        <slot name="left">
          <BrandMark v-if="brand" :size="'sm'" />
        </slot>
      </view>
      <view class="nav-title-wrap" :style="{ right: rightReserve + 'px' }">
        <text v-if="title" class="nav-title">{{ title }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
// 自定义导航栏：按状态栏高度 + 胶囊按钮位置算高度，避免被胶囊压住/遮挡
// 任务书 §8：自定义导航栏要避让胶囊。
import { ref, onMounted } from 'vue';
import BrandMark from './BrandMark.vue';

defineOptions({ name: 'NavBar' });

defineProps({
  title: { type: String, default: '' },
  brand: { type: Boolean, default: false },
  showBack: { type: Boolean, default: false },
});

const statusBarHeight = ref(20);
const navHeight = ref(44);
const rightReserve = ref(96);

onMounted(() => {
  let sysHeight = 20;
  try {
    const sys = uni.getSystemInfoSync() || {};
    sysHeight = sys.statusBarHeight || 20;
  } catch (e) {
    sysHeight = 20;
  }
  statusBarHeight.value = sysHeight;

  // 胶囊按钮位置：导航栏高度 = 胶囊上下留白 + 胶囊高
  let menu = null;
  try {
    // #ifdef MP-WEIXIN || MP-TOUTIAO
    menu = uni.getMenuButtonBoundingClientRect && uni.getMenuButtonBoundingClientRect();
    // #endif
  } catch (e) {
    menu = null;
  }

  if (menu && menu.height && menu.top) {
    const gap = menu.top - sysHeight; // 胶囊距离状态栏底部的间距
    navHeight.value = menu.height + gap * 2;
    // 标题居中区域要避开右侧胶囊
    let windowWidth = 375;
    try {
      windowWidth = (uni.getSystemInfoSync() || {}).windowWidth || 375;
    } catch (e) {
      windowWidth = 375;
    }
    rightReserve.value = Math.max(0, windowWidth - menu.left + 8);
  } else {
    // 非小程序端或拿不到胶囊时给个保守值
    navHeight.value = 44;
    rightReserve.value = 96;
  }
});

function goBack() {
  uni.navigateBack({
    fail: () => uni.switchTab({ url: '/pages/index/index' }),
  });
}
</script>

<style lang="scss" scoped>
.nav-wrap {
  width: 100%;
  background-color: $bg;
}

.nav-bar {
  position: relative;
  display: flex;
  flex-direction: row;
  align-items: center;
  padding-left: 39rpx;
}

.nav-left {
  display: flex;
  flex-direction: row;
  align-items: center;
  z-index: 2;
}

.nav-back {
  width: 84rpx;
  height: 84rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: -20rpx;
  z-index: 2;
}

// 返回箭头：M15 6l-6 6 6 6，用两条 1.8 描边的边代替
.back-icon {
  width: 18rpx;
  height: 18rpx;
  border-left: 3rpx solid $ink;
  border-bottom: 3rpx solid $ink;
  transform: rotate(45deg);
}

.nav-title-wrap {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.nav-title {
  font-size: 33rpx;
  font-weight: 700;
  color: $ink;
  max-width: 400rpx;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
