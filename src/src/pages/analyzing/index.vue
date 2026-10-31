<template>
  <view class="page">
    <NavBar title="检查中" />

    <!-- 三灯：全产品唯一的动画（任务书 §6.2） -->
    <view class="lamp-box">
      <view class="lamp-row">
        <view class="lamp-slot" :class="{ lit: litIndex === 0 }">
          <view class="lamp-dot red"></view>
        </view>
        <view class="lamp-slot" :class="{ lit: litIndex === 1 }">
          <view class="lamp-dot amber"></view>
        </view>
        <view class="lamp-slot" :class="{ lit: litIndex === 2 }">
          <view class="lamp-dot green"></view>
        </view>
      </view>
    </view>

    <!-- 当前真实阶段文案 -->
    <text class="stage">{{ stageText }}</text>
    <text class="stage-sub">{{ subText }}</text>

    <!-- 超过 30 秒 -->
    <view v-if="slow" class="slow-box">
      <text class="slow-text">有点慢，分析完会出现在检查记录里</text>
      <view class="btn-line" @tap="goHome"><text>先回首页</text></view>
    </view>

    <text class="disclaimer">{{ disclaimer }}</text>
  </view>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import NavBar from '@/components/NavBar.vue';
import { fetchAnalysis, ApiError } from '@/services/api.js';
import { refreshUser } from '@/services/session.js';
import { DISCLAIMER_TEXT } from '@/common/constants.js';

defineOptions({ name: 'AnalyzingPage' });

// 四个真实阶段（不放假进度条）
// 路线调整令：三段真实阶段（原来第四段「正在写报告」去掉，一期不生成新文字，只拼模板）
const STAGES = ['正在读截图', '正在比对套路库', '正在逐项检查'];

const DEFAULT_POLL_MS = 1500;
const LOCAL_BACKGROUND_MS = 30 * 1000;

const taskId = ref('');
const status = ref('pending');
const stageIndex = ref(0);
const litIndex = ref(0);
const elapsedMs = ref(0);
const slow = ref(false);
const finished = ref(false);
const disclaimer = DISCLAIMER_TEXT;

let pollTimer = null;
let animTimer = null;
let clockTimer = null;
let startedAt = 0;
let lastDelay = DEFAULT_POLL_MS;

const stageText = computed(() => {
  if (status.value === 'pending') return '正在排队';
  return STAGES[Math.min(stageIndex.value, STAGES.length - 1)];
});

const subText = computed(() => {
  if (status.value === 'pending') return '马上开始';
  return '一般 10–30 秒出结果';
});

// 三灯依次亮起循环，同时推进阶段文案
function startLampLoop() {
  animTimer = setInterval(() => {
    litIndex.value = (litIndex.value + 1) % 3;
    if (stageIndex.value < STAGES.length - 1) stageIndex.value += 1;
  }, 900);
}

function scheduleNext(ms) {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(poll, ms || DEFAULT_POLL_MS);
}

function poll() {
  if (finished.value) return;
  fetchAnalysis(taskId.value)
    .then((res) => {
      status.value = res.status || 'pending';
      if (typeof res.elapsed_ms === 'number') elapsedMs.value = res.elapsed_ms;

      // 以服务端字段为准；缺失时才用本地 30 秒兜底
      if (typeof res.background_mode === 'boolean') {
        slow.value = res.background_mode;
      } else if (elapsedMs.value >= LOCAL_BACKGROUND_MS) {
        slow.value = true;
      }

      if (res.status === 'done' && res.report) {
        finish();
        refreshUser().catch(() => {});
        uni.redirectTo({ url: '/pages/report/index?report_id=' + res.report.report_id });
        return;
      }

      if (res.status === 'failed') {
        finish();
        refreshUser().catch(() => {});
        uni.showModal({
          title: '这次检查没成功',
          content: res.error_message || '次数已经退回，可以重新上传再试',
          showCancel: false,
          success: () => uni.navigateBack({ fail: () => uni.switchTab({ url: '/pages/index/index' }) }),
        });
        return;
      }

      if (res.status === 'running' && stageIndex.value < 1) stageIndex.value = 1;
      scheduleNext(slow.value ? 5000 : res.poll_after_ms || DEFAULT_POLL_MS);
    })
    .catch((err) => {
      if (err instanceof ApiError && err.code === 'NOT_FOUND') {
        finish();
        uni.showModal({
          title: '检查任务不存在',
          content: '这个任务已过期或被清理，请重新上传截图。',
          showCancel: false,
          success: () => uni.switchTab({ url: '/pages/index/index' }),
        });
        return;
      }
      lastDelay = Math.min(8000, lastDelay * 2);
      scheduleNext(lastDelay);
    });
}

function finish() {
  finished.value = true;
  stopAll();
}

function stopAll() {
  if (pollTimer) clearTimeout(pollTimer);
  if (animTimer) clearInterval(animTimer);
  if (clockTimer) clearInterval(clockTimer);
  pollTimer = null;
  animTimer = null;
  clockTimer = null;
}

onMounted(() => {
  const pages = getCurrentPages();
  const current = pages[pages.length - 1];
  taskId.value = (current && current.options && current.options.task_id) || '';
  startedAt = Date.now();

  startLampLoop();
  clockTimer = setInterval(() => {
    if (finished.value) return;
    elapsedMs.value = Date.now() - startedAt;
    if (elapsedMs.value >= LOCAL_BACKGROUND_MS && !slow.value) slow.value = true;
  }, 1000);

  if (!taskId.value) {
    uni.showModal({
      title: '没有检查任务',
      content: '请先回首页上传截图。',
      showCancel: false,
      success: () => uni.switchTab({ url: '/pages/index/index' }),
    });
    return;
  }
  poll();
});

onUnmounted(stopAll);

function goHome() {
  uni.switchTab({ url: '/pages/index/index' });
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background-color: $bg;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 39rpx;
}

// 三灯在底座上
.lamp-box {
  margin-top: 190rpx;
  background-color: $housing;
  border: 2rpx solid $line;
  border-radius: 46rpx;
  padding: 60rpx 50rpx;
}

.lamp-row {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.lamp-slot {
  width: 120rpx;
  height: 120rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.28;

  & + & {
    margin-left: 40rpx;
  }

  &.lit {
    opacity: 1;
  }
}

.lamp-dot {
  width: 85rpx;
  height: 85rpx;
  border-radius: 50%;

  &.red {
    background-color: $red;
  }
  &.amber {
    background-color: $amber;
  }
  &.green {
    background-color: $green;
  }
}

// 亮起时才发光
.lamp-slot.lit .lamp-dot.red {
  box-shadow: 0 0 0 12rpx $red-soft, 0 0 42rpx $red;
}
.lamp-slot.lit .lamp-dot.amber {
  box-shadow: 0 0 0 12rpx $amber-soft, 0 0 42rpx $amber;
}
.lamp-slot.lit .lamp-dot.green {
  box-shadow: 0 0 0 12rpx $green-soft, 0 0 42rpx $green;
}

.stage {
  margin-top: 77rpx;
  font-size: 46rpx;
  font-weight: 900;
  color: $ink;
}

.stage-sub {
  margin-top: 15rpx;
  font-size: 27rpx;
  color: $ink-2;
}

.slow-box {
  margin-top: 77rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.slow-text {
  font-size: 27rpx;
  color: $ink-2;
  text-align: center;
}

.btn-line {
  margin-top: 31rpx;
  height: 100rpx;
  padding: 0 61rpx;
  border-radius: 31rpx;
  border: 3rpx solid $outline;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 31rpx;
    font-weight: 700;
    color: $ink;
  }
}

.disclaimer {
  margin-top: auto;
  margin-bottom: calc(60rpx + env(safe-area-inset-bottom));
  font-size: 23rpx;
  color: $ink-2;
  text-align: center;
  line-height: 1.6;
}
</style>
