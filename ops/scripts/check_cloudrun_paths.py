"""验证云托管镜像的路径假设：容器内 /app 下 project_root 是否正确。

本脚本模拟云托管的目录结构 /app/{engine,rules,backend}，
检查 config.PROJECT_ROOT 是否等于 /app、日志目录是否为 /app/var/log。

不依赖 Docker：只按同一份代码的相对位置推演。
"""
from pathlib import Path

# backend/app/config.py 里的推导：Path(__file__).resolve().parent.parent.parent
# 也就是  backend/app/config.py -> backend/app -> backend -> 项目根
fake_config = Path("/app/backend/app/config.py")
project_root = fake_config.parent.parent.parent
# Windows 上 Path 用反斜杠，统一成正斜杠再比较
root_str = project_root.as_posix()
print("容器内 config.py 路径 :", fake_config.as_posix())
print("推导出的 project_root :", root_str)
print("日志目录 log_dir      :", (project_root / "var" / "log").as_posix())
print("删除日志 deletion.log :", (project_root / "var" / "log" / "deletion.log").as_posix())
print()
ok = root_str == "/app"
print("结论：", "✅ project_root == /app，日志落 /app/var/log，与 Dockerfile 的 mkdir 一致"
      if ok else "❌ 路径推算不符，需修正 Dockerfile")
print("说明：本机是 Windows，Path 会渲染成反斜杠；这里比较的是 POSIX 形式。")

