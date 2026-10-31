<template>
  <view class="page">
    <NavBar title="求助详情" show-back />

    <view v-if="!enabled" class="main">
      <view class="card closed">
        <text class="closed-title">广场还没开放</text>
        <view class="btn-line" @tap="goSquare"><text>回广场</text></view>
      </view>
    </view>

    <view v-else class="main">
      <view v-if="loading" class="loading"><text>加载中…</text></view>

      <view v-else>
        <!-- 帖子主体 -->
        <view class="card post">
          <view class="post-head">
            <text class="post-company">{{ post.company }}</text>
            <SignalLamp v-if="post.risk_overall" :level="post.risk_overall" size="sm" />
          </view>
          <text class="post-line">{{ post.position }} · {{ post.city }}</text>
          <text class="post-q">{{ post.question }}</text>
          <text class="post-nick">{{ post.anonymous_nick }} · {{ shortTime(post.created_at) }}</text>

          <view v-if="post.ai_summary || post.risk_overall" class="ai-box">
            <text class="ai-label">自动检查结论（只针对截图内容）</text>
            <text class="ai-text">{{ post.ai_summary || overallText }}</text>
          </view>
        </view>

        <!-- 投票区 -->
        <text class="h2">你会怎么建议</text>
        <view class="card vote-card">
          <view class="vote-btns">
            <view class="vote-btn vote-btn-up" :class="{ on: myVote === 1 }" @tap="vote(1)">
              <text>建议去</text>
            </view>
            <view class="vote-btn vote-btn-down" :class="{ on: myVote === -1 }" @tap="vote(-1)">
              <text>不建议去</text>
            </view>
          </view>

          <!-- 投完可以选理由标签 -->
          <view v-if="myVote !== 0" class="reasons">
            <text class="reasons-title">选个理由（可不选）</text>
            <view class="reason-list">
              <view
                v-for="r in reasonTags"
                :key="r.key"
                class="reason-item"
                :class="{ on: myReason === r.key }"
                @tap="pickReason(r.key)"
              >
                <text>{{ r.name }}</text>
              </view>
            </view>
          </view>

          <!-- 投票条 -->
          <view class="vote-bar">
            <view class="vote-fill" :style="{ width: upPercent + '%' }"></view>
          </view>
          <view class="vote-meta">
            <text class="vote-up">{{ post.vote_up }} 人建议去</text>
            <text class="vote-down">{{ post.vote_down }} 人不建议</text>
          </view>
        </view>

        <!-- 大家的经历 -->
        <text class="h2">大家的经历</text>
        <view v-if="!experiences.length" class="card empty-exp">
          <text class="empty-t">还没有人分享经历</text>
        </view>
        <view v-for="e in experiences" :key="e.id" class="card exp">
          <text class="exp-text">{{ e.content }}</text>
          <view class="exp-foot">
            <text class="exp-time">{{ shortTime(e.created_at) }}</text>
            <text class="exp-report" @tap="report(e.id)">举报</text>
          </view>
        </view>

        <!-- 写经历 -->
        <view class="card write-box">
          <textarea
            class="write-input"
            v-model="expContent"
            placeholder="说说你的经历，只写事实，不写「骗子」这类结论"
            placeholder-class="write-ph"
            maxlength="500"
          />
          <view class="btn-line" @tap="submitExperience"><text>提交经历</text></view>
        </view>

        <!-- 免责 + 企业申诉 -->
        <view class="bottom-note">
          <text class="note-text"
            >广场内容由用户发布，只代表个人经历，不代表平台对任何企业的评价。自动检查结论只针对截图内容。</text
          >
          <view class="appeal-entry" @tap="openAppeal"><text>企业申诉入口</text></view>
        </view>
      </view>
    </view>

    <!-- 举报 / 申诉弹层 -->
    <view v-if="sheet === 'report'" class="mask" @tap="closeSheet">
      <view class="sheet" @tap.stop>
        <text class="sheet-title">举报这条内容</text>
        <view class="reason-list">
          <view
            v-for="r in reportReasons"
            :key="r"
            class="reason-item"
            :class="{ on: reportReason === r }"
            @tap="reportReason = r"
          >
            <text>{{ r }}</text>
          </view>
        </view>
        <view class="btn-primary" @tap="submitReport"><text>提交举报</text></view>
        <text class="sheet-cancel" @tap="closeSheet">取消</text>
      </view>
    </view>

    <view v-if="sheet === 'appeal'" class="mask" @tap="closeSheet">
      <view class="sheet" @tap.stop>
        <text class="sheet-title">企业申诉</text>
        <text class="sheet-desc">企业认为内容不实，可以在这里提出，我们 24 小时内处理。</text>
        <input class="sheet-input" v-model="appealCompany" placeholder="企业全称" placeholder-class="write-ph" />
        <input class="sheet-input" v-model="appealContact" placeholder="联系方式" placeholder-class="write-ph" />
        <textarea
          class="sheet-textarea"
          v-model="appealContent"
          placeholder="请说明申诉理由"
          placeholder-class="write-ph"
          maxlength="500"
        />
        <view class="btn-primary" @tap="submitAppeal"><text>提交申诉</text></view>
        <text class="sheet-cancel" @tap="closeSheet">取消</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import NavBar from '@/components/NavBar.vue';
import SignalLamp from '@/components/SignalLamp.vue';
import {
  fetchPostDetail,
  fetchExperiences,
  createExperience,
  votePost,
  reportPost,
  createAppeal,
  isCommunityClosed,
} from '@/services/api.js';

defineOptions({ name: 'PostDetailPage' });

const postId = ref('');
const post = ref({});
const experiences = ref([]);
const enabled = ref(true);
const loading = ref(true);
const myVote = ref(0);
const myReason = ref('');
const expContent = ref('');
const sheet = ref('');
const reportReason = ref('内容不实');
const appealCompany = ref('');
const appealContact = ref('');
const appealContent = ref('');

// 理由标签（后台可配置，前端先固定）
const reasonTags = [
  { key: 'fee', name: '我也被要求过交钱' },
  { key: 'mismatch', name: '岗位和说的不一样' },
  { key: 'normal', name: '面试流程正常' },
  { key: 'other', name: '其他' },
];

const reportReasons = ['内容不实', '辱骂攻击', '泄露隐私', '广告引流', '其他'];

const OVERALL_TEXT = {
  red: '截图里存在需要先弄清楚的收费或工作内容问题',
  amber: '截图里有需要先问清楚的地方',
  green: '截图里没看到明显风险',
  unknown: '截图信息不够，不好判断',
};
const overallText = computed(() => OVERALL_TEXT[post.value.risk_overall] || '暂无结论');

const upPercent = computed(() => {
  const up = Number(post.value.vote_up || 0);
  const down = Number(post.value.vote_down || 0);
  const total = up + down;
  if (!total) return 50;
  return Math.round((up / total) * 100);
});

function shortTime(s) {
  const m = String(s || '').match(/(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  return m ? m[2] + '-' + m[3] + ' ' + m[4] + ':' + m[5] : String(s || '');
}

function load() {
  loading.value = true;
  fetchPostDetail(postId.value)
    .then((p) => {
      post.value = p || {};
      myVote.value = Number(p.my_vote || 0);
      return fetchExperiences(postId.value);
    })
    .then((res) => {
      experiences.value = (res && res.items) || [];
    })
    .catch((err) => {
      if (isCommunityClosed(err)) enabled.value = false;
      else if (err && err.code === 'NOT_FOUND') {
        uni.showToast({ title: '帖子不存在或已隐藏', icon: 'none' });
      }
    })
    .then(() => {
      loading.value = false;
    });
}

onMounted(() => {
  const pages = getCurrentPages();
  const current = pages[pages.length - 1];
  const options = (current && current.options) || {};
  postId.value = options.id || '';
  if (!postId.value) {
    uni.showToast({ title: '缺少帖子 ID', icon: 'none' });
    loading.value = false;
    return;
  }
  load();
});

// 投票：一人一票可改，再点同一项 = 取消
function vote(value) {
  const next = myVote.value === value ? 0 : value;
  votePost(postId.value, next, myReason.value)
    .then((res) => {
      myVote.value = Number(res.my_vote || 0);
      post.value.vote_up = res.vote_up;
      post.value.vote_down = res.vote_down;
      if (next === 0) {
        myReason.value = '';
        uni.showToast({ title: '已取消投票', icon: 'none' });
      } else {
        uni.showToast({ title: '已记录你的投票', icon: 'none' });
      }
    })
    .catch((err) => {
      uni.showToast({ title: errorText(err), icon: 'none' });
    });
}

function pickReason(key) {
  myReason.value = myReason.value === key ? '' : key;
  // 有投票时把理由一起带上
  if (myVote.value !== 0) {
    votePost(postId.value, myVote.value, myReason.value).catch(() => {});
  }
}

function submitExperience() {
  const text = expContent.value.trim();
  if (!text) {
    uni.showToast({ title: '先写点什么', icon: 'none' });
    return;
  }
  createExperience(postId.value, text)
    .then(() => {
      expContent.value = '';
      uni.showToast({ title: '已提交，审核通过后显示', icon: 'none' });
    })
    .catch((err) => {
      uni.showToast({ title: errorText(err), icon: 'none' });
    });
}

function report(experienceId) {
  reportReason.value = '内容不实';
  sheet.value = 'report';
  void experienceId;
}

function submitReport() {
  reportPost(postId.value, reportReason.value)
    .then(() => {
      sheet.value = '';
      uni.showToast({ title: '已收到举报，我们会尽快处理', icon: 'none' });
    })
    .catch((err) => {
      uni.showToast({ title: errorText(err), icon: 'none' });
    });
}

function openAppeal() {
  sheet.value = 'appeal';
}

function submitAppeal() {
  if (!appealCompany.value.trim() || !appealContent.value.trim()) {
    uni.showToast({ title: '请填写企业全称和申诉理由', icon: 'none' });
    return;
  }
  createAppeal({
    post_id: postId.value,
    company: appealCompany.value.trim(),
    contact: appealContact.value.trim(),
    content: appealContent.value.trim(),
  })
    .then((res) => {
      sheet.value = '';
      uni.showModal({
        title: '申诉已提交',
        content: '我们会在 ' + ((res && res.sla_hours) || 24) + ' 小时内处理。',
        showCancel: false,
      });
    })
    .catch((err) => {
      uni.showToast({ title: errorText(err), icon: 'none' });
    });
}

function closeSheet() {
  sheet.value = '';
}

// 错误码 → 大白话（docs/10 3.3）
function errorText(err) {
  const code = err && err.code;
  const map = {
    NEW_ACCOUNT_RESTRICTED: '账号注册还不满 24 小时，暂时不能发帖和投票',
    CONTENT_BLOCKED: '内容没通过审核，请改成描述事实',
    FORBIDDEN: '不能给自己的帖子投票',
    NOT_FOUND: '内容不存在或已隐藏',
  };
  return map[code] || (err && err.message) || '操作失败';
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

.loading {
  padding: 77rpx 0;
  text-align: center;

  text {
    font-size: 27rpx;
    color: $ink-2;
  }
}

.post {
  margin-top: 23rpx;
  padding: 35rpx;
}

.post-head {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.post-company {
  flex: 1;
  margin-right: 15rpx;
  font-size: 38rpx;
  font-weight: 900;
  color: $ink;
}

.post-line {
  margin-top: 8rpx;
  font-size: 25rpx;
  color: $ink-2;
  display: block;
}

.post-q {
  margin-top: 23rpx;
  font-size: 31rpx;
  line-height: 1.65;
  color: $ink-3;
  display: block;
}

.post-nick {
  margin-top: 23rpx;
  font-size: 23rpx;
  color: $off-text;
  display: block;
}

// 自动检查结论框
.ai-box {
  margin-top: 27rpx;
  background-color: $surface-2;
  border-radius: 23rpx;
  padding: 23rpx;
}

.ai-label {
  font-size: 21rpx;
  color: $brand-text;
  display: block;
}

.ai-text {
  margin-top: 8rpx;
  font-size: 27rpx;
  line-height: 1.6;
  color: $ink-3;
  display: block;
}

.h2 {
  margin-top: 54rpx;
  margin-bottom: 23rpx;
  font-size: 33rpx;
  font-weight: 800;
  color: $ink;
  display: block;
}

// 投票
.vote-card {
  padding: 31rpx;
}

.vote-btns {
  display: flex;
  flex-direction: row;
}

.vote-btn {
  flex: 1;
  height: 100rpx;
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

.vote-btn-up {
  margin-right: 19rpx;

  &.on {
    border-color: $green;
    background-color: $green-soft;

    text {
      color: $green-text;
    }
  }
}

.vote-btn-down.on {
  border-color: $amber;
  background-color: $amber-soft;

  text {
    color: $amber-text;
  }
}

.reasons {
  margin-top: 31rpx;
}

.reasons-title {
  font-size: 25rpx;
  color: $ink-2;
  display: block;
}

.reason-list {
  margin-top: 19rpx;
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
}

.reason-item {
  padding: 15rpx 27rpx;
  border-radius: 27rpx;
  background-color: $surface-2;
  margin: 0 15rpx 15rpx 0;

  text {
    font-size: 25rpx;
    color: $ink-2;
  }

  &.on {
    background-color: $brand-soft;

    text {
      color: $brand-text;
      font-weight: 700;
    }
  }
}

.vote-bar {
  margin-top: 31rpx;
  height: 12rpx;
  border-radius: 6rpx;
  background-color: $amber-soft;
  overflow: hidden;
}

.vote-fill {
  height: 100%;
  background-color: $green;
  border-radius: 6rpx;
}

.vote-meta {
  margin-top: 15rpx;
  display: flex;
  flex-direction: row;
  justify-content: space-between;

  text {
    font-size: 23rpx;
  }
}

.vote-up {
  color: $green-text;
}

.vote-down {
  color: $amber-text;
}

// 经历
.empty-exp {
  padding: 46rpx 31rpx;
}

.empty-t {
  font-size: 27rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}

.exp {
  margin-top: 19rpx;
  padding: 31rpx;
}

.exp-text {
  font-size: 27rpx;
  line-height: 1.7;
  color: $ink-3;
  display: block;
}

.exp-foot {
  margin-top: 19rpx;
  display: flex;
  flex-direction: row;
  justify-content: space-between;
}

.exp-time {
  font-size: 21rpx;
  color: $off-text;
}

.exp-report {
  font-size: 21rpx;
  color: $ink-2;
}

// 写经历
.write-box {
  margin-top: 27rpx;
  padding: 31rpx;
}

.write-input {
  width: 100%;
  height: 160rpx;
  background-color: $surface-2;
  border-radius: 23rpx;
  padding: 23rpx;
  font-size: 27rpx;
  color: $ink;
  box-sizing: border-box;
}

.write-ph {
  color: $off-text;
}

.btn-line {
  margin-top: 23rpx;
  height: 92rpx;
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

.bottom-note {
  margin-top: 54rpx;
  padding: 31rpx;
  background-color: $surface-2;
  border-radius: 31rpx;
}

.note-text {
  font-size: 23rpx;
  line-height: 1.7;
  color: $ink-2;
  display: block;
}

.appeal-entry {
  margin-top: 19rpx;
  height: 85rpx;
  border-radius: 27rpx;
  border: 3rpx solid $outline;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 27rpx;
    font-weight: 700;
    color: $ink-3;
  }
}

// 弹层
.mask {
  position: fixed;
  left: 0;
  top: 0;
  right: 0;
  bottom: 0;
  background-color: $housing;
  opacity: 0.98;
  display: flex;
  align-items: flex-end;
  z-index: 99;
}

.sheet {
  width: 100%;
  background-color: $surface;
  border-radius: 46rpx 46rpx 0 0;
  padding: 42rpx 39rpx calc(31rpx + env(safe-area-inset-bottom));
}

.sheet-title {
  font-size: 38rpx;
  font-weight: 900;
  color: $ink;
  text-align: center;
  display: block;
}

.sheet-desc {
  margin-top: 15rpx;
  font-size: 25rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}

.sheet-input {
  margin-top: 23rpx;
  height: 92rpx;
  background-color: $surface-2;
  border-radius: 23rpx;
  padding: 0 23rpx;
  font-size: 27rpx;
  color: $ink;
}

.sheet-textarea {
  margin-top: 19rpx;
  width: 100%;
  height: 160rpx;
  background-color: $surface-2;
  border-radius: 23rpx;
  padding: 23rpx;
  font-size: 27rpx;
  color: $ink;
  box-sizing: border-box;
}

.btn-primary {
  margin-top: 31rpx;
  height: 100rpx;
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

.sheet-cancel {
  margin-top: 23rpx;
  font-size: 27rpx;
  color: $ink-2;
  text-align: center;
  display: block;
}
</style>
