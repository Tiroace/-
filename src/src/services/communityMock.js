// 求助广场 mock 层（R3）
//
// 重要：社区按 D14 **默认关闭**。mock 层也遵守这条：
// 只有本地存储 qiuzhibilei_mock_community = '1' 时才返回数据，否则抛 NOT_FOUND，
// 与真后端「开关关闭 → 404」的行为一致，前端走同一条隐藏分支。
// 用途：产品/老板想预览社区页面时打开这个开关，不需要起真后端。
import { ApiError } from '@/services/api.js';

const MOCK_ON_KEY = 'qiuzhibilei_mock_community';

function communityOn() {
  try {
    return uni.getStorageSync(MOCK_ON_KEY) === '1';
  } catch (e) {
    return false;
  }
}

function closed() {
  throw new ApiError('NOT_FOUND', '社区未开放');
}

function delay(ms = 200) {
  return new Promise((r) => setTimeout(r, ms));
}

// 帖子样本：内容是虚构的，不指向任何真实企业（合规要求）
const POSTS = [
  {
    id: 'p1',
    company: '某科技公司',
    position: '运营专员',
    city: '杭州',
    question: '说要先交 300 元工装费，说是入职后退，这种正常吗？',
    risk_overall: 'red',
    vote_up: 12,
    vote_down: 28,
    experience_count: 5,
    my_vote: 0,
    created_at: '2026-10-30 20:15:00',
    anonymous_nick: '匿名用户 3F2A',
  },
  {
    id: 'p2',
    company: '某贸易公司',
    position: '管培生',
    city: '上海',
    question: '岗位写管培生，面试说主要做电话回访，这算名不副实吗？',
    risk_overall: 'amber',
    vote_up: 9,
    vote_down: 11,
    experience_count: 3,
    my_vote: 1,
    created_at: '2026-10-30 15:40:00',
    anonymous_nick: '匿名用户 8C1D',
  },
  {
    id: 'p3',
    company: '某网络公司',
    position: '客服',
    city: '深圳',
    question: '面试全程没提薪资，只说综合 8k 起，要不要去？',
    risk_overall: 'amber',
    vote_up: 6,
    vote_down: 4,
    experience_count: 1,
    my_vote: 0,
    created_at: '2026-10-29 10:02:00',
    anonymous_nick: '匿名用户 5A77',
  },
];

const EXPERIENCES = {
  p1: [
    { id: 'e1', content: '我也遇到过要工装费的，交了之后就没下文了，建议别交。', useful: 8, my_vote: 1, created_at: '2026-10-30 21:10:00' },
    { id: 'e2', content: '正规公司不会在入职前收钱，直接走人。', useful: 5, my_vote: -1, created_at: '2026-10-30 22:02:00' },
  ],
  p2: [{ id: 'e3', content: '这家我去面过，确实是打电话，管培生只是名字。', useful: 3, my_vote: 0, created_at: '2026-10-30 16:20:00' }],
  p3: [],
};

// GET /community/posts
export function mockListPosts({ sort = 'latest', q = '', limit = 20 } = {}) {
  if (!communityOn()) return Promise.all([closed()]);
  return delay().then(() => {
    let list = POSTS.slice();
    if (q) {
      const kw = String(q).trim();
      list = list.filter(
        (p) =>
          p.company.includes(kw) || p.position.includes(kw) || p.city.includes(kw) || p.question.includes(kw)
      );
    }
    if (sort === 'active') {
      list.sort((a, b) => b.vote_up + b.vote_down - (a.vote_up + a.vote_down));
    } else if (sort === 'voted') {
      list = list.filter((p) => p.my_vote !== 0);
    } else {
      list.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    }
    return { items: list.slice(0, limit), next_cursor: null };
  });
}

// GET /community/posts/{id}
export function mockPostDetail(postId) {
  if (!communityOn()) return Promise.all([closed()]);
  return delay().then(() => {
    const p = POSTS.find((x) => x.id === postId);
    if (!p) throw new ApiError('NOT_FOUND', '帖子不存在');
    return p;
  });
}

// POST /community/posts
export function mockCreatePost(payload) {
  if (!communityOn()) return Promise.all([closed()]);
  return delay(300).then(() => ({
    id: 'p_new_' + Date.now(),
    status: 'pending',
    message: '已提交审核',
  }));
}

// POST /community/posts/{id}/vote
export function mockVote(postId, value, reason) {
  if (!communityOn()) return Promise.all([closed()]);
  return delay().then(() => {
    const p = POSTS.find((x) => x.id === postId);
    if (!p) throw new ApiError('NOT_FOUND', '帖子不存在');
    const prev = p.my_vote;
    if (prev === 1) p.vote_up -= 1;
    if (prev === -1) p.vote_down -= 1;
    if (value === 1) p.vote_up += 1;
    if (value === -1) p.vote_down += 1;
    p.my_vote = value;
    return { post_id: postId, my_vote: value, vote_up: p.vote_up, vote_down: p.vote_down, reason: reason || '' };
  });
}

// GET /community/posts/{id}/experiences
export function mockExperiences(postId) {
  if (!communityOn()) return Promise.all([closed()]);
  return delay().then(() => ({ items: EXPERIENCES[postId] || [] }));
}

// POST /community/posts/{id}/experiences
export function mockCreateExperience(postId, content) {
  if (!communityOn()) return Promise.all([closed()]);
  return delay(300).then(() => ({ id: 'e_new', status: 'pending', content }));
}

// POST /community/posts/{id}/report
export function mockReport(postId, reason) {
  if (!communityOn()) return Promise.all([closed()]);
  return delay().then(() => ({ received: true, reason: reason || '' }));
}

// POST /community/appeals
export function mockAppeal(payload) {
  if (!communityOn()) return Promise.all([closed()]);
  return delay().then(() => ({
    id: 'ap_new',
    status: 'open',
    sla_hours: 24,
    post_id: payload && payload.post_id,
  }));
}
