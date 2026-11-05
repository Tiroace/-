<template>
  <!-- 规则版用的上传卡空实现（构建期替换，见 vite.config.js 的 alias）。
       规则版首页只有粘贴卡，上传卡永远不渲染；留一个空组件是为了让 import 合法，
       同时保证「点这里选截图」「再加一张」这些上传卡文案不进入规则版产物。 -->
  <view />
</template>

<script setup>
defineOptions({ name: 'UploadCardStub' });
</script>
