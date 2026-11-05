<template>
  <!-- 上传卡（老板 2026-11-05 双版本令第四节第 3 条）：只属于识图版首页。
       整张卡都能点；中间是插画 + 「点这里选截图」；选了图后插画收起，只留缩略图和按钮。 -->
  <view class="card upload upload-card" :class="{ 'upload-card-has': images.length }" @tap="onTapCard">
    <!-- 已选截图缩略图（可删除）：选图后插画收起，这里是唯一内容区 -->
    <view v-if="images.length" class="thumbs thumbs-in-card">
      <view v-for="(img, idx) in images" :key="img.path" class="thumb">
        <image class="thumb-img" :src="img.path" mode="aspectFill" />
        <view class="thumb-del" @tap.stop="$emit('remove', idx)">
          <text class="thumb-del-text">×</text>
        </view>
      </view>
      <view v-if="images.length < maxImages" class="thumb thumb-add" @tap.stop="$emit('pick')">
        <text class="thumb-add-plus">+</text>
        <text class="thumb-add-t">再加一张</text>
      </view>
    </view>

    <!-- 插画 + 引导文案：选了图就收起来，只留缩略图和按钮 -->
    <view v-if="!images.length" class="upload-dashed">
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

      <text class="up-title">点这里选截图</text>
      <text class="up-sub">最多 {{ maxImages }} 张，岗位详情和聊天记录一起传更准</text>
    </view>

    <view class="btn-primary" :class="{ 'btn-busy': submitting }" @tap.stop="$emit('start')">
      <text>{{ buttonText }}</text>
    </view>

    <view class="up-meta">
      <text v-if="isUnlimited">内测期间不限次数</text>
      <text v-else>还能免费查 <text class="up-meta-num">{{ balance }}</text> 次</text>
      <text>没查出结果，不扣次数</text>
    </view>
  </view>
</template>

<script setup>
// 这个组件只被识图版首页引入。规则版首页是粘贴卡，不会 import 本文件，
// 所以规则版产物里不会出现「点这里选截图」这类上传文案（check-rules-build.mjs 会核对）。
import { computed } from 'vue';

const props = defineProps({
  images: { type: Array, default: () => [] },
  submitting: { type: Boolean, default: false },
  balance: { type: Number, default: 0 },
  isUnlimited: { type: Boolean, default: false },
  maxImages: { type: Number, default: 3 },
});

const emit = defineEmits(['pick', 'remove', 'start']);

const buttonText = computed(() => {
  if (props.submitting) return '正在检查…';
  if (props.images.length) return '开始检查（' + props.images.length + ' 张）';
  return '选截图，开始检查';
});

// 整张卡都能点：没满 3 张就继续选
function onTapCard() {
  if (props.submitting) return;
  if (props.images.length < props.maxImages) emit('pick');
}
</script>

<style lang="scss" scoped>

.upload {
  margin-top: 46rpx;
  border-radius: 46rpx;
  padding: 38rpx;
  background-color: $surface;
}

// 整张卡都能点，虚线框
.upload-card {
  border: 3rpx dashed $off;
}
.upload-dashed {
  display: block;
}
.thumbs {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
}
.thumbs-in-card {
  margin-top: 0;
  margin-bottom: 19rpx;
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
}
.thumb-del {
  position: absolute;
  top: 0;
  right: 0;
  width: 44rpx;
  height: 44rpx;
  border-bottom-left-radius: 19rpx;
  background-color: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
}
.thumb-del-text {
  color: $ink;
  font-size: 30rpx;
  line-height: 1;
}
.thumb-add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2rpx dashed $off;
  background-color: $surface-2;
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

// 插画区
.illus {
  position: relative;
  height: 246rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.shot {
  position: absolute;
  border-radius: 19rpx;
  background-color: $surface-2;
}
.shot.l {
  width: 130rpx;
  height: 190rpx;
  left: 60rpx;
  transform: rotate(-8deg);
  opacity: 0.5;
}
.shot.r {
  width: 130rpx;
  height: 190rpx;
  right: 60rpx;
  transform: rotate(8deg);
  opacity: 0.5;
}
.shot.m {
  width: 170rpx;
  height: 230rpx;
  padding: 23rpx 19rpx;
  box-sizing: border-box;
}
.bar-line {
  height: 13rpx;
  border-radius: 7rpx;
  background-color: $off;
  margin-bottom: 15rpx;
}
.bar-line.hit {
  background-color: $amber;
}
.bang {
  position: absolute;
  right: 200rpx;
  top: 20rpx;
  width: 44rpx;
  height: 44rpx;
  border-radius: 22rpx;
  background-color: $red;
  color: $ink;
  font-size: 27rpx;
  font-weight: 800;
  text-align: center;
  line-height: 44rpx;
}

.up-title {
  margin-top: 31rpx;
  font-size: 33rpx;
  font-weight: 700;
  color: $ink;
  display: block;
  text-align: center;
}
.up-sub {
  margin-top: 15rpx;
  font-size: 25rpx;
  color: $ink-2;
  display: block;
  text-align: center;
}

.btn-primary {
  margin-top: 31rpx;
  height: $btn-h;
  border-radius: $radius-btn;
  background-color: $amber;
  display: flex;
  align-items: center;
  justify-content: center;
  color: $cta-ink;
  font-weight: 800;
  font-size: 31rpx;
}
.btn-busy {
  opacity: 0.6;
}

.up-meta {
  margin-top: 19rpx;
  display: flex;
  flex-direction: row;
  justify-content: center;
  flex-wrap: wrap;
}
.up-meta text {
  font-size: $fs-small;
  color: $ink-2;
  margin-left: 19rpx;
}
.up-meta-num {
  color: $amber;
  font-weight: 800;
}
</style>
