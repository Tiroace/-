<template>
  <view class="page">
    <NavBar title="发起求助" show-back />

    <view v-if="!enabled" class="main">
      <view class="card closed">
        <text class="closed-title">广场还没开放</text>
        <view class="btn-line" @tap="goSquare"><text>回广场</text></view>
      </view>
    </view>

    <view v-else class="main">
      <!-- ① 必须关联一份检查记录 -->
      <text class="h2">关联检查记录</text>
      <view v-if="!reports.length" class="card need-check">
        <text class="need-t">还没有检查记录</text>
        <text class="need-s">先上传招聘截图做一次检查，再来广场求助。</text>
        <view class="btn-line" @tap="goIndex"><text>去检查</text></view>
      </view>

      <view v-else class="card report-list">
        <view
          v-for="(r, idx) in reports"
          :key="r.report_id"
          class="report-item"
          :class="{ on: selectedReport === r.report_id, 'item-last': idx === reports.length - 1 }"
          @tap="selectedReport = r.report_id"
        >
          <SignalLamp :level="overallToLamp(r.risk_level)" size="sm" />
          <view class="grow">
            <text class="report-summary">{{ r.summary }}</text>
            <text class="report-date">{{ r.created_at }}</text>
          </view>
          <view class="radio" :class="{ checked: selectedReport === r.report_id }"></view>
        </view>
      </view>

      <!-- ② 打码预览 -->
      <text class="h2">截图打码预览</text>
      <view class="card mask-box">
        <text class="mask-tip">截图里的手机号、微信号、身份证号会自动打码。如果还有要遮住的地方，可以点「补充打码」。</text>
        <view class="mask-preview">
          <text class="mask-text">{{ maskPreviewText }}</text>
        </view>
        <view class="btn-line" @tap="toggleMask"><text>补充打码</text></view>
      </view>

      <!-- ③ 表单 -->
      <text class="h2">填一下情况</text>
      <view class="card form">
        <text class="label">公司名称</text>
        <input class="input" v-model="company" placeholder="从截图识别，可修改" placeholder-class="ph" />

        <text class="label">职位</text>
        <input class="input" v-model="position" placeholder="例如：运营专员" placeholder-class="ph" />

        <text class="label">城市</text>
        <input class="input" v-model="city" placeholder="例如：杭州" placeholder-class="ph" />

        <view class="label-row">
          <text class="label">你想问什么</text>
          <text class="counter" :class="{ over: question.length > MAX_Q }">{{ question.length }}/200</text>
        </view>
        <textarea
          class="textarea"
          v-model="question"
          :maxlength="MAX_Q"
          placeholder="说清楚你遇到的情况，比如对方提了什么要求"
          placeholder-class="ph"
        />

        <text class="hint">写事实，不写「骗子」这类结论。比如写「要求入职前交 300 元」，不写「这家是骗子」。</text>
      </view>

      <!-- ④ 匿名 + 承诺 -->
      <view class="card opts">
        <view class="opt-row" @tap="anonymous = !anonymous">
          <view class="grow">
            <text class="opt-t">匿名发布</text>
            <text class="opt-s">别人只看到随机昵称，看不到你是谁</text>
          </view>
          <switch :checked="anonymous" :color="SWITCH_COLOR" @change="anonymous = $event.detail.value" />
        </view>

        <view class="opt-row opt-row-last" @tap="promised = !promised">
          <view class="checkbox" :class="{ checked: promised }"></view>
          <text class="opt-t">确认是真实经历，并已阅读社区规范</text>
        </view>
      </view>

      <view class="btn-primary" :class="{ busy: submitting }" @tap="submit">
        <text>{{ submitting ? '提交中…' : '提交审核' }}</text>
      </view>
      <!-- 审核说明：只写结论，不承诺审核时效（老板要求；等异步自动审核上线后再按实际口径调整） -->
      <text class="review-note">审核通过后公开</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import NavBar from '@/components/NavBar.vue';
import SignalLamp from '@/components/SignalLamp.vue';
import { fetchReports, createPost, isCommunityClosed } from '@/services/api.js';
import { SWITCH_COLOR } from '@/common/brand.js';

defineOptions({ name: 'PostCreatePage' });

const MAX_Q = 200;

const enabled = ref(true);
const reports = ref([]);
const selectedReport = ref('');
const company = ref('');
const position = ref('');
const city = ref('');
const question = ref('');
const anonymous = ref(true); // 默认打开（任务书 §6.8）
const promised = ref(false);
const submitting = ref(false);
const maskOn = ref(false);

// 打码预览：真环境由后端返回打码后的截图；这里用文案示意
const maskPreviewText = computed(() => {
  if (!maskOn.value) return '截图里的手机号、微信号、身份证号已自动打码';
  return '已补充打码：你在截图上点选的位置也会被遮住';
});

function overallToLamp(level) {
  const map = { high: 'red', red: 'red', warn: 'amber', amber: 'amber', notice: 'amber', safe: 'green', green: 'green' };
  return map[level] || 'off';
}

onMounted(() => {
  fetchReports({ limit: 20 })
    .then((res) => {
      reports.value = (res && res.items) || [];
      if (reports.value.length) selectedReport.value = reports.value[0].report_id;
    })
    .catch((err) => {
      if (isCommunityClosed(err)) enabled.value = false;
    });
});

function toggleMask() {
  maskOn.value = !maskOn.value;
}

function submit() {
  if (submitting.value) return;
  if (!selectedReport.value) {
    uni.showToast({ title: '先选一份检查记录', icon: 'none' });
    return;
  }
  if (!company.value.trim() || !position.value.trim()) {
    uni.showToast({ title: '公司名称和职位要填', icon: 'none' });
    return;
  }
  if (!question.value.trim()) {
    uni.showToast({ title: '说说你想问什么', icon: 'none' });
    return;
  }
  if (!promised.value) {
    uni.showToast({ title: '请先勾选「确认是真实经历」', icon: 'none' });
    return;
  }
  submitting.value = true;
  createPost({
    report_id: selectedReport.value,
    company: company.value.trim(),
    position: position.value.trim(),
    city: city.value.trim(),
    question: question.value.trim(),
    anonymous: anonymous.value,
    mask_supplement: maskOn.value,
  })
    .then(() => {
      submitting.value = false;
      uni.showModal({
        title: '已提交审核',
        content: '审核通过后会显示在广场里。',
        showCancel: false,
        success: () => uni.navigateBack({ fail: () => uni.switchTab({ url: '/pages/square/index' }) }),
      });
    })
    .catch((err) => {
      submitting.value = false;
      const code = err && err.code;
      const map = {
        NEW_ACCOUNT_RESTRICTED: '账号注册还不满 24 小时，暂时不能发帖',
        CONTENT_BLOCKED: '内容里有不合适的说法，请改成描述事实',
      };
      uni.showToast({ title: map[code] || (err && err.message) || '提交失败', icon: 'none' });
    });
}

function goIndex() {
  uni.switchTab({ url: '/pages/index/index' });
}

function goSquare() {
  uni.switchTab({ url: '/pages/square/index' });
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background-color: $bg;
}

.main {
  padding: 0 39rpx;
  padding-bottom: calc(60rpx + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
}

.card {
  background-color: $surface;
  border-radius: 38rpx;
}

.closed {
  margin-top: 150rpx;
  padding: 77rpx 39rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.closed-title {
  font-size: 38rpx;
  font-weight: 900;
  color: $ink;
}

.h2 {
  margin-top: 46rpx;
  margin-bottom: 19rpx;
  font-size: 31rpx;
  font-weight: 800;
  color: $ink;
  display: block;
}

// 没有检查记录
.need-check {
  padding: 46rpx 31rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.need-t {
  font-size: 29rpx;
  font-weight: 700;
  color: $ink;
}

.need-s {
  margin-top: 12rpx;
  font-size: 25rpx;
  color: $ink-2;
  text-align: center;
}

// 检查记录选择
.report-list {
  padding: 8rpx 31rpx;
}

.report-item {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 27rpx 0;
  border-bottom: 2rpx solid $divider;

  &.item-last {
    border-bottom: none;
  }

  &.on .report-summary {
    color: $brand-text;
  }
}

.grow {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  margin-left: 19rpx;
}

.report-summary {
  font-size: 27rpx;
  color: $ink;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.report-date {
  margin-top: 6rpx;
  font-size: 21rpx;
  color: $off-text;
}

.radio {
  width: 34rpx;
  height: 34rpx;
  border-radius: 50%;
  border: 3rpx solid $outline;
  flex-shrink: 0;
  margin-left: 15rpx;

  &.checked {
    border-color: $cta;
    background-color: $cta;
  }
}

// 打码预览
.mask-box {
  padding: 31rpx;
}

.mask-tip {
  font-size: 25rpx;
  line-height: 1.6;
  color: $ink-2;
  display: block;
}

.mask-preview {
  margin-top: 23rpx;
  height: 200rpx;
  background-color: $housing;
  border-radius: 23rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 23rpx;
}

.mask-text {
  font-size: 25rpx;
  color: $ink-3;
  text-align: center;
}

// 表单
.form {
  padding: 31rpx;
}

.label {
  margin-top: 23rpx;
  font-size: 25rpx;
  color: $ink-2;
  display: block;

  &:first-child {
    margin-top: 0;
  }
}

.label-row {
  margin-top: 23rpx;
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  align-items: center;
}

.counter {
  font-size: 23rpx;
  color: $off-text;

  &.over {
    color: $red;
  }
}

.input {
  margin-top: 12rpx;
  height: 92rpx;
  background-color: $surface-2;
  border-radius: 23rpx;
  padding: 0 23rpx;
  font-size: 27rpx;
  color: $ink;
}

.textarea {
  margin-top: 12rpx;
  width: 100%;
  height: 200rpx;
  background-color: $surface-2;
  border-radius: 23rpx;
  padding: 23rpx;
  font-size: 27rpx;
  color: $ink;
  box-sizing: border-box;
}

.ph {
  color: $off-text;
}

.hint {
  margin-top: 19rpx;
  font-size: 23rpx;
  line-height: 1.6;
  color: $ink-2;
  display: block;
}

// 选项
.opts {
  margin-top: 27rpx;
  padding: 0 31rpx;
}

.opt-row {
  padding: 27rpx 0;
  display: flex;
  flex-direction: row;
  align-items: center;
  border-bottom: 2rpx solid $divider;

  &.opt-row-last {
    border-bottom: none;
  }
}

.opt-t {
  font-size: 27rpx;
  color: $ink;
}

.opt-s {
  margin-top: 6rpx;
  font-size: 23rpx;
  color: $ink-2;
}

.checkbox {
  width: 36rpx;
  height: 36rpx;
  border-radius: 9rpx;
  border: 3rpx solid $outline;
  margin-right: 19rpx;
  flex-shrink: 0;

  &.checked {
    background-color: $cta;
    border-color: $cta;
  }
}

.btn-primary {
  margin-top: 39rpx;
  height: 108rpx;
  border-radius: 31rpx;
  background-color: $cta;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 33rpx;
    font-weight: 900;
    color: $cta-ink;
  }

  &.busy {
    opacity: 0.7;
  }
}

.btn-line {
  margin-top: 23rpx;
  height: 92rpx;
  padding: 0 46rpx;
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

// 审核说明：提交按钮正下方，只写结论不写时效
.review-note {
  margin-top: 23rpx;
  font-size: 23rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}
</style>
