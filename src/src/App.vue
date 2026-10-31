<script>
// 应用根组件：只做全局样式与启动初始化，业务逻辑都在页面和适配层里。
import { ensureLogin } from '@/services/session.js';
import { currentPlatform } from '@/platform/index.js';

export default {
  onLaunch() {
    console.log('[启动] 平台=', currentPlatform.platform, '运行时=', currentPlatform.runtime);
    // 静默登录：失败不阻断进入首页，用户点「选截图」时再要求登录
    ensureLogin().catch((e) => {
      console.log('[启动] 静默登录失败，稍后重试：', e && e.message);
    });
  },
};
</script>

<style lang="scss">
// 全局基础样式（深色「夜间信号」配色，全部取 uni.scss 的变量）
page {
  background-color: $bg;
  color: $ink;
  font-size: 29rpx;
  line-height: 1.6;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
}

view,
text {
  box-sizing: border-box;
  word-break: break-word;
}

// 通用工具类
.card {
  background-color: $surface;
  border-radius: 38rpx;
}

.row {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.row-between {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.col {
  display: flex;
  flex-direction: column;
}

.grow {
  flex: 1;
  min-width: 0;
}

.text-muted {
  color: $ink-2;
}

.text-small {
  font-size: 23rpx;
}

.title {
  font-size: 33rpx;
  font-weight: 800;
  color: $ink;
}

// 主按钮：品牌黄
.btn-primary {
  background-color: $cta;
  color: $cta-ink;
  border-radius: 31rpx;
  text-align: center;
  padding: 28rpx 0;
  font-size: 33rpx;
  font-weight: 900;

  &.disabled {
    opacity: 0.6;
  }
}

// 次要按钮：描边
.btn-ghost {
  background-color: transparent;
  color: $ink;
  border: 3rpx solid $outline;
  border-radius: 31rpx;
  text-align: center;
  padding: 26rpx 0;
  font-size: 31rpx;
  font-weight: 700;
}

.btn-gray {
  background-color: $surface-2;
  color: $ink;
  border-radius: 27rpx;
  text-align: center;
  padding: 26rpx 0;
  font-size: 29rpx;
}

.link {
  color: $brand-text;
  font-size: 27rpx;
}

.divider {
  height: 2rpx;
  background-color: $divider;
  margin: 23rpx 0;
}

// 灯色文字
.level-high {
  color: $red;
}
.level-warn {
  color: $amber;
}
.level-notice {
  color: $amber-text;
}
.level-safe {
  color: $green;
}
.level-unknown {
  color: $ink-2;
}

.tag {
  display: inline-block;
  padding: 6rpx 15rpx;
  border-radius: 15rpx;
  font-size: 23rpx;
  margin-right: 12rpx;
  margin-bottom: 12rpx;
}
</style>
