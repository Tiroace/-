<template>
  <view class="page">
    <NavBar title="求助广场" />

    <!-- 社区未开放：整页隐藏入口（D14），不显示「开发中」 -->
    <view v-if="!enabled" class="main">
      <view class="card closed">
        <view class="logo">
          <view class="bar"></view>
          <view class="bar"></view>
        </view>
        <text class="closed-title">广场还没开放</text>
        <text class="closed-desc">先去检查一份工作，结果随时能看。</text>
        <view class="btn-line" @tap="goIndex"><text>去检查</text></view>
      </view>
    </view>

    <view v-else class="main">
      <!-- 搜索 -->
      <view class="search-bar">
        <input
          class="search-input"
          v-model="keyword"
          placeholder="搜公司名、岗位或城市"
          placeholder-class="search-ph"
          confirm-type="search"
          @confirm="doSearch"
        />
        <view class="search-btn" @tap="doSearch"><text>搜索</text></view>
      </view>

      <!-- 排序 -->
      <view class="sorts">
        <view
          v-for="s in sorts"
          :key="s.key"
          class="sort-item"
          :class="{ on: sort === s.key }"
          @tap="changeSort(s.key)"
        >
          <text>{{ s.name }}</text>
        </view>
      </view>

      <!-- 列表 -->
      <view v-if="loading" class="loading"><text>加载中…</text></view>

      <view v-else-if="!posts.length" class="card empty">
        <text class="empty-t">{{ emptyText }}</text>
        <view class="btn-line" @tap="gotoCreate"><text>发起求助</text></view>
      </view>

      <view v-else>
        <view v-for="p in posts" :key="p.id" class="card post" @tap="openPost(p.id)">
          <view class="post-head">
            <text class="post-company">{{ p.company }}</text>
            <SignalLamp v-if="p.risk_overall" :level="p.risk_overall" size="sm" />
          </view>
          <text class="post-line">{{ p.position }} · {{ p.city }}</text>
          <text class="post-q">{{ p.question }}</text>

          <!-- 投票条 -->
          <view class="vote-bar">
            <view class="vote-fill" :style="{ width: upPercent(p) + '%' }"></view>
          </view>
          <view class="vote-meta">
            <text class="vote-up">{{ p.vote_up }} 人建议去</text>
            <text class="vote-down">{{ p.vote_down }} 人不建议</text>
          </view>
          <text class="post-foot">{{ p.experience_count }} 条经历 · {{ shortTime(p.created_at) }}</text>
        </view>
      </view>

      <text class="note">广场内容由用户发布，只代表个人经历，不代表平台对任何企业的评价。</text>
    </view>

    <!-- 右下角发起求助 -->
    <view v-if="enabled" class="fab" @tap="gotoCreate">
      <text class="fab-text">＋</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import NavBar from '@/components/NavBar.vue';
import SignalLamp from '@/components/SignalLamp.vue';
import { fetchPosts } from '@/services/api.js';
import { probeCommunity } from '@/common/features.js';

defineOptions({ name: 'SquarePage' });

const enabled = ref(false);
const posts = ref([]);
const loading = ref(false);
const keyword = ref('');
const sort = ref('latest');

const sorts = [
  { key: 'latest', name: '最新' },
  { key: 'active', name: '参与最多' },
  { key: 'voted', name: '我投过的' },
];

const emptyText = computed(() => {
  if (sort.value === 'voted') return '还没有你投过票的帖子';
  if (keyword.value) return '没搜到相关内容';
  return '还没有人求助';
});

// 建议去人数占比例（票数都 0 时给 50%）
function upPercent(p) {
  const total = Number(p.vote_up || 0) + Number(p.vote_down || 0);
  if (!total) return 50;
  return Math.round((Number(p.vote_up || 0) / total) * 100);
}

// 时间：MM-DD HH:mm
function shortTime(s) {
  const m = String(s || '').match(/(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  return m ? m[2] + '-' + m[3] + ' ' + m[4] + ':' + m[5] : String(s || '');
}

function load() {
  loading.value = true;
  fetchPosts({ sort: sort.value, q: keyword.value, limit: 20 })
    .then((res) => {
      posts.value = (res && res.items) || [];
    })
    .catch((err) => {
      posts.value = [];
      // 404 = 社区未开放，隐藏整页
      if (err && err.code === 'NOT_FOUND') enabled.value = false;
    })
    .then(() => {
      loading.value = false;
    });
}

onMounted(() => {
  probeCommunity().then((on) => {
    enabled.value = on;
    if (on) load();
  });
});

function doSearch() {
  load();
}

function changeSort(key) {
  if (sort.value === key) return;
  sort.value = key;
  load();
}

function openPost(id) {
  uni.navigateTo({ url: '/pages/post/index?id=' + id });
}

function gotoCreate() {
  uni.navigateTo({ url: '/pages/post-create/index' });
}

function goIndex() {
  uni.switchTab({ url: '/pages/index/index' });
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background-color: $bg;
}

.main {
  padding: 0 39rpx;
  padding-bottom: calc(220rpx + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
}

// 未开放
.closed {
  margin-top: 150rpx;
  padding: 77rpx 39rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo {
  width: 108rpx;
  height: 108rpx;
  border-radius: 33rpx;
  background-color: $cta;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
}

.bar {
  width: 14rpx;
  height: 46rpx;
  border-radius: 7rpx;
  background-color: $cta-ink;

  & + & {
    margin-left: 14rpx;
  }
}

.closed-title {
  margin-top: 38rpx;
  font-size: 38rpx;
  font-weight: 900;
  color: $ink;
}

.closed-desc {
  margin-top: 15rpx;
  font-size: 27rpx;
  color: $ink-2;
  text-align: center;
}

// 搜索
.search-bar {
  margin-top: 23rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
}

.search-input {
  flex: 1;
  height: 92rpx;
  background-color: $surface;
  border-radius: 27rpx;
  padding: 0 31rpx;
  font-size: 27rpx;
  color: $ink;
}

.search-ph {
  color: $off-text;
}

.search-btn {
  margin-left: 19rpx;
  height: 92rpx;
  padding: 0 35rpx;
  border-radius: 27rpx;
  background-color: $cta;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 29rpx;
    font-weight: 900;
    color: $cta-ink;
  }
}

// 排序
.sorts {
  margin-top: 27rpx;
  display: flex;
  flex-direction: row;
}

.sort-item {
  padding: 15rpx 31rpx;
  border-radius: 27rpx;
  background-color: $surface;
  margin-right: 19rpx;

  text {
    font-size: 27rpx;
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

.loading {
  padding: 77rpx 0;
  text-align: center;

  text {
    font-size: 27rpx;
    color: $ink-2;
  }
}

.card {
  background-color: $surface;
  border-radius: 38rpx;
}

.empty {
  margin-top: 46rpx;
  padding: 61rpx 39rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.empty-t {
  font-size: 29rpx;
  color: $ink-2;
}

// 帖子卡
.post {
  margin-top: 23rpx;
  padding: 31rpx;
}

.post-head {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.post-company {
  font-size: 33rpx;
  font-weight: 800;
  color: $ink;
  flex: 1;
  margin-right: 15rpx;
}

.post-line {
  margin-top: 8rpx;
  font-size: 25rpx;
  color: $ink-2;
  display: block;
}

.post-q {
  margin-top: 19rpx;
  font-size: 29rpx;
  line-height: 1.6;
  color: $ink-3;
  display: block;
}

// 投票条
.vote-bar {
  margin-top: 27rpx;
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

.post-foot {
  margin-top: 15rpx;
  font-size: 23rpx;
  color: $ink-2;
  display: block;
}

.btn-line {
  margin-top: 46rpx;
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

.note {
  margin-top: 46rpx;
  font-size: 23rpx;
  line-height: 1.6;
  color: $ink-2;
  text-align: center;
}

// 右下角发起求助
.fab {
  position: fixed;
  right: 39rpx;
  bottom: calc(60rpx + env(safe-area-inset-bottom));
  width: 115rpx;
  height: 115rpx;
  border-radius: 50%;
  background-color: $cta;
  display: flex;
  align-items: center;
  justify-content: center;
}

.fab-text {
  font-size: 61rpx;
  font-weight: 900;
  color: $cta-ink;
  line-height: 1;
}
</style>
