<template>
  <view class="page">
    <view class="card doc-card">
      <text class="doc-title">{{ doc.title }}</text>
      <text class="doc-note" v-if="doc.note">{{ doc.note }}</text>
      <view class="divider"></view>
      <view v-for="(sec, idx) in doc.sections" :key="idx" class="section">
        <text class="section-title">{{ sec.h }}</text>
        <text class="section-body">{{ sec.p }}</text>
      </view>
    </view>

    <!-- 意见反馈表单 -->
    <view v-if="type === 'feedback'" class="card form-card">
      <text class="title">意见反馈</text>
      <view class="reason-list">
        <view
          v-for="t in fbTypes"
          :key="t.key"
          class="reason-item"
          :class="{ selected: fbType === t.key }"
          @tap="fbType = t.key"
        >
          <text class="reason-text">{{ t.label }}</text>
        </view>
      </view>
      <textarea
        class="textarea"
        v-model="fbContent"
        placeholder="说说是哪里不对劲，或者你希望增加什么功能（可选）"
        maxlength="500"
      />
      <view class="btn-primary" @tap="submitFb"><text>提交反馈</text></view>
    </view>

    <!-- 申诉表单 -->
    <view v-if="type === 'appeal'" class="card form-card">
      <text class="title">申诉入口</text>
      <text class="text-muted form-tip"
        >如果你（企业或个人）对某份报告有异议，可以在这里提出。我们会在 7 个工作日内答复。</text
      >
      <view class="reason-list">
        <view
          v-for="t in appealTypes"
          :key="t.key"
          class="reason-item"
          :class="{ selected: appealType === t.key }"
          @tap="appealType = t.key"
        >
          <text class="reason-text">{{ t.label }}</text>
        </view>
      </view>
      <textarea
        class="textarea"
        v-model="appealContent"
        placeholder="请写明报告编号、你认为有问题的地方，以及你的联系方式（我们会脱敏处理）"
        maxlength="500"
      />
      <view class="btn-primary" @tap="submitAppeal"><text>提交申诉</text></view>
    </view>

    <view class="footer-disclaimer">
      <text>{{ disclaimer }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { submitFeedback } from '@/services/api.js';
import { DISCLAIMER_TEXT } from '@/common/constants.js';
import { PRIVACY_DOC, RULES_DOC } from '@/common/docTexts.js';

defineOptions({ name: 'DocPage' });

const type = ref('privacy');
const disclaimer = DISCLAIMER_TEXT;

const fbTypes = [
  { key: 'inaccurate', label: '判断不准' },
  { key: 'suggest', label: '改进建议' },
];
const fbType = ref('suggest');
const fbContent = ref('');

const appealTypes = [
  { key: 'enterprise', label: '我是企业方' },
  { key: 'person', label: '我是个人' },
];
const appealType = ref('enterprise');
const appealContent = ref('');

// 文档正文：正式版本由产品经理在 docs/06 定稿、律师审核后替换（当前为占位草稿，不得对公众发布）
const DOCS = {
  // 隐私政策与检查规则说明按引擎选用（双版本令第二节第 4 条）：
  // 规则版全部在手机上跑，截图不上传；DeepSeek 版会把截图发给第三方，必须写清楚。
  privacy: PRIVACY_DOC,
  agreement: {
    title: '用户协议',
    note: '草稿占位：正式文本待产品经理出具、律师审核后替换',
    sections: [
      {
        h: '1. 服务内容',
        p: '本产品对招聘信息截图做自动检查，输出风险提示报告。报告仅供参考，不构成法律意见，不代表对任何企业的评价。',
      },
      {
        h: '2. 使用规则',
        p: '请勿上传违法内容。你上传截图即表示你确认有权使用该截图。',
      },
      {
        h: '3. 次数怎么获得',
        p: '新用户注册赠送 3 次。看一次激励视频可增加 1 次，每天上限 5 次。本产品目前完全免费，没有任何收费项目。',
      },
      {
        h: '4. 广告说明',
        p: '是否需要观看广告，由你在次数用完时自行选择。任何功能都不会强制你观看广告；广告没加载出来时，我们会直接给你次数。',
      },
      {
        h: '5. 免责',
        p: '报告由系统根据截图文字和规则库自动生成，可能存在偏差。请结合实际情况自行判断，重要决定建议咨询专业人士。',
      },
    ],
  },
  // 检查规则说明（替代原「服务公示」页）：按引擎选用
  ai: RULES_DOC,
  feedback: {
    title: '意见反馈',
    note: '',
    sections: [],
  },
  appeal: {
    title: '申诉流程',
    note: '',
    sections: [
      {
        h: '谁能提',
        p: '企业和个人都可以提。',
      },
      {
        h: '怎么提',
        p: '在报告页点「申诉入口」，或在「我的 → 申诉入口」里填写。请写明报告编号和问题点。',
      },
      {
        h: '多久答复',
        p: '目标 7 个工作日内答复。涉及高危报告的，我们会同时提示 110 报警、96110 反诈专线、12333 劳动权益咨询。',
      },
    ],
  },
};

const doc = computed(() => DOCS[type.value] || DOCS.privacy);

onMounted(() => {
  const pages = getCurrentPages();
  const current = pages[pages.length - 1];
  const options = (current && current.options) || {};
  type.value = options.type || 'privacy';
});

function submitFb() {
  submitFeedback({ type: fbType.value, content: fbContent.value }).then(() => {
    fbContent.value = '';
    uni.showToast({ title: '已提交，感谢反馈', icon: 'none' });
  });
}

function submitAppeal() {
  submitFeedback({ type: 'appeal', appeal_from: appealType.value, content: appealContent.value }).then(
    () => {
      appealContent.value = '';
      uni.showModal({
        title: '申诉已提交',
        content: '我们会在 7 个工作日内答复。',
        showCancel: false,
      });
    }
  );
}
</script>

<style scoped>
.doc-card {
  padding: 32rpx 28rpx;
}

.doc-title {
  font-size: 36rpx;
  font-weight: 700;
  display: block;
}

.doc-note {
  display: block;
  font-size: 22rpx;
  color: $amber;
  background-color: $brand-soft;
  padding: 10rpx 16rpx;
  border-radius: 8rpx;
  margin-top: 16rpx;
}

.section {
  margin-bottom: 28rpx;
}

.section-title {
  display: block;
  font-size: 28rpx;
  font-weight: 600;
  margin-bottom: 8rpx;
}

.section-body {
  display: block;
  font-size: 26rpx;
  color: $ink-3;
  line-height: 1.7;
}

.form-card {
  margin-top: 0;
}

.form-tip {
  display: block;
  margin: 12rpx 0 20rpx;
}

.reason-list {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  margin-top: 16rpx;
}

.reason-item {
  padding: 14rpx 24rpx;
  border-radius: 12rpx;
  background-color: $surface-2;
  margin: 0 16rpx 16rpx 0;
}

.reason-item.selected {
  background-color: $brand-soft;
  border: 2rpx solid $cta;
}

.reason-text {
  font-size: 24rpx;
  color: $ink-3;
}

.reason-item.selected .reason-text {
  color: $cta;
}

.textarea {
  width: 100%;
  height: 200rpx;
  background-color: $surface-2;
  border-radius: 12rpx;
  padding: 20rpx;
  font-size: 26rpx;
  margin-bottom: 24rpx;
}

.footer-disclaimer {
  padding: 16rpx 40rpx 40rpx;
  font-size: 22rpx;
  color: $ink-2;
  text-align: center;
  line-height: 1.6;
}
</style>
