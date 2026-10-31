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
  privacy: {
    title: '隐私政策',
    note: '草稿占位：正式文本待产品经理出具、律师审核后替换',
    sections: [
      {
        h: '1. 我们收集什么',
        p: '你上传的招聘信息截图，以及分析生成的报告文字。我们不收集你的手机号，不获取定位信息。',
      },
      {
        h: '2. 截图怎么处理',
        p: '截图仅用于本次分析。分析完成后 24 小时内删除原图，不在客户端保存截图副本。',
      },
      {
        h: '3. 报告保存多久',
        p: '报告文字普通用户保存 7 天，会员保存 30 天，到期自动清除。',
      },
      {
        h: '4. 第三方的个人信息',
        p: '截图里可能出现 HR 的姓名、电话、微信号。日志和报告中这类信息一律脱敏处理，不做长期保存。',
      },
      {
        h: '5. 数据存在哪里',
        p: '全部数据存储在中国境内，不出境。',
      },
      {
        h: '6. 「判断不准」留样',
        p: '你点「判断不准」时，我们会单独弹窗征求你的同意；你同意后，才会把这次截图留作改进识别效果的样本。不同意也能提交反馈。',
      },
    ],
  },
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
        h: '3. 次数与会员',
        p: '新用户注册赠送 3 次。看一次激励视频可增加 1 次，每天上限 5 次。会员拼的是每日更多次数与更长的报告保存时间。',
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
  // 检查规则说明（替代原「服务公示」页；路线调整令后不使用大模型）
  ai: {
    title: '检查规则说明',
    note: '草稿：正文待产品经理出具、律师审核后替换',
    sections: [
      {
        h: '1. 怎么检查',
        p: '你上传的截图会先被读成文字，然后逐句和规则库、套路库比对。比对上的会列出来，每条都附截图原文，你能直接对照。',
      },
      {
        h: '2. 规则从哪来',
        p: '规则来自公开的劳动法规条文和公开的反诈宣传案例。每条规则都写明了：命中的原文、为什么有风险、涉及哪条法规、面试前该问 HR 什么、自己怎么核实。',
      },
      {
        h: '3. 可能漏判',
        p: '规则是固定的，看不懂就没有提示。换个说法、图片太模糊、截图不完整，都可能漏掉问题。检查通过不代表一定安全，一定要自己再核实一遍。',
      },
      {
        h: '4. 报告怎么生成',
        p: '报告只把命中的规则原文和对应的说明拼起来，不会自己编造内容。每条发现都能在截图里找到对应的字。',
      },
      {
        h: '5. 内容安全',
        p: '上传图片先经内容安全检测；报告展示前会过滤不合适的表述，不使用定性、诋毁性的说法。',
      },
    ],
  },
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
