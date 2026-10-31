// 自动化链路冒烟工程：只验证「IDE 能否打开 + automator 能否连上 + 点击/断言能否跑通」
App({
  globalData: {
    launchedAt: Date.now()
  },
  onLaunch() {
    this.globalData.launched = true
  }
})
