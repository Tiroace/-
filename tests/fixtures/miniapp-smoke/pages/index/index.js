// 冒烟页：给自动化提供可点击、可断言的最小元素
Page({
  data: {
    count: 0,
    greeting: '冒烟页已加载',
    // 故意留一个「模拟提交」按钮，用来验证 automator 的点击 + 数据回读
    submitted: null
  },

  onTapInc() {
    this.setData({ count: this.data.count + 1 })
  },

  onTapSubmit() {
    this.setData({ submitted: 'ok' })
  }
})
