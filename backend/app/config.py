"""后端配置。所有可调参数走环境变量，默认值按原型期约定。

额度与价格口径来自需求书 §6.1 / §6.3，未拍板前按「建议」列执行（docs/02）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/app/config.py → 项目根


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# 默认口令：只在本地联调时可用。生产环境（QBL_ENV=prod）检测到任何一个没换，就拒绝启动。
DEFAULT_SECRETS = {
    "token_secret": "dev-token-secret-change-me",
    "pay_secret": "dev-pay-secret-change-me",
    "admin_token": "dev-admin-token",
}


class InsecureProductionConfig(RuntimeError):
    """生产环境仍在用默认口令：必须拒绝启动，不能带着默认口令上线。"""


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    db_path: Path = field(default_factory=lambda: _env_path("QBL_DB_PATH", PROJECT_ROOT / "var" / "backend" / "qbl.db"))
    upload_dir: Path = field(default_factory=lambda: _env_path("QBL_UPLOAD_DIR", PROJECT_ROOT / "var" / "uploads"))
    report_dir: Path = field(default_factory=lambda: _env_path("QBL_REPORT_DIR", PROJECT_ROOT / "var" / "reports"))
    cache_dir: Path = field(default_factory=lambda: _env_path("QBL_CACHE_DIR", PROJECT_ROOT / "var" / "cache" / "dedupe"))

    # 鉴权与回调签名：生产必须换成真实密钥（走安全卡片），默认值只用于本地联调
    token_secret: str = field(default_factory=lambda: os.environ.get("QBL_TOKEN_SECRET", "dev-token-secret-change-me"))
    pay_secret: str = field(default_factory=lambda: os.environ.get("QBL_PAY_SECRET", "dev-pay-secret-change-me"))
    admin_token: str = field(default_factory=lambda: os.environ.get("QBL_ADMIN_TOKEN", "dev-admin-token"))
    token_ttl_seconds: int = 7 * 24 * 3600

    # 额度（§6.1）
    free_quota: int = field(default_factory=lambda: _env_int("QBL_FREE_QUOTA", 3))
    ad_daily_cap: int = field(default_factory=lambda: _env_int("QBL_AD_DAILY_CAP", 5))
    member_daily_quota: int = field(default_factory=lambda: _env_int("QBL_MEMBER_DAILY_QUOTA", 20))

    # 会员价格（§6.3，单位：分）
    prices_fen: dict = field(default_factory=lambda: {"week": 690, "month": 1990, "quarter": 3990})
    plan_days: dict = field(default_factory=lambda: {"week": 7, "month": 30, "quarter": 90})

    # 单笔支付上限（风控：单笔 ≤ 300 元）
    max_order_amount_fen: int = field(default_factory=lambda: _env_int("QBL_MAX_ORDER_AMOUNT_FEN", 30000))

    # 截图上传有效期（§8：分析完成 24 小时内删原图，隐私政策维持「24 小时内」口径不改）
    # 取 22 小时：清理任务每小时扫一次，最坏在到期后 1 小时内被删，
    # 22h TTL + ≤1h 扫描延迟 ⇒ 从上传算起删除时间 ≤23h，给「24 小时内」留 1 小时余量。
    # （23h 时最坏是 24h，卡在边界上没有余量；整点字符串比较可能再晚一点。）
    upload_ttl_hours: int = field(default_factory=lambda: _env_int("QBL_UPLOAD_TTL_HOURS", 22))

    # 报告保存期限（§8）：普通 7 天、会员 30 天
    report_ttl_days: int = 7
    member_report_ttl_days: int = 30

    # 接口限流（原型期用进程内计数）
    analysis_per_minute: int = 10

    # 异步分析（D5：POST 立即返回 task_id，前端轮询 GET /analysis/{id}）
    worker_threads: int = field(default_factory=lambda: _env_int("QBL_WORKER_THREADS", 4))
    poll_after_ms: int = field(default_factory=lambda: _env_int("QBL_POLL_AFTER_MS", 1500))
    background_after_seconds: int = field(default_factory=lambda: _env_int("QBL_BACKGROUND_AFTER_SECONDS", 30))
    # 仅测试用：给引擎加人为延迟，用来验证 running 状态与「30 秒转后台」语义
    fake_engine_delay_ms: int = field(default_factory=lambda: _env_int("QBL_FAKE_ENGINE_DELAY_MS", 0))

    # 开发登录通道（code=mock 直接换 token）：默认关，仅本地联调用 QBL_DEV_MODE=1 打开
    dev_mode: bool = field(default_factory=lambda: os.environ.get("QBL_DEV_MODE", "0") == "1")

    # 求助广场（D14：默认关闭，资质核实后再开）
    feature_community: bool = field(default_factory=lambda: os.environ.get("QBL_FEATURE_COMMUNITY", "0") == "1")
    community_new_account_hours: int = field(default_factory=lambda: _env_int("QBL_COMMUNITY_NEW_ACCOUNT_HOURS", 24))
    community_report_hide_threshold: int = field(default_factory=lambda: _env_int("QBL_COMMUNITY_REPORT_HIDE_THRESHOLD", 3))
    community_appeal_sla_hours: int = field(default_factory=lambda: _env_int("QBL_COMMUNITY_APPEAL_SLA_HOURS", 24))
    community_post_max_len: int = field(default_factory=lambda: _env_int("QBL_COMMUNITY_POST_MAX_LEN", 200))
    # D18 防刷：窗口期内同设备/同网段投票超阈值 → 可疑票（counted=0，不计展示，保留记录）
    community_vote_window_minutes: int = field(default_factory=lambda: _env_int("QBL_COMMUNITY_VOTE_WINDOW_MINUTES", 10))
    community_vote_device_limit: int = field(default_factory=lambda: _env_int("QBL_COMMUNITY_VOTE_DEVICE_LIMIT", 5))
    community_vote_ip_limit: int = field(default_factory=lambda: _env_int("QBL_COMMUNITY_VOTE_IP_LIMIT", 20))

    # 平台凭据（没配就用 Mock 适配器；生产走安全卡片注入）
    tt_appid: str = field(default_factory=lambda: os.environ.get("QBL_TT_APPID", ""))
    tt_secret: str = field(default_factory=lambda: os.environ.get("QBL_TT_SECRET", ""))
    wx_appid: str = field(default_factory=lambda: os.environ.get("QBL_WX_APPID", ""))
    wx_secret: str = field(default_factory=lambda: os.environ.get("QBL_WX_SECRET", ""))
    tt_ad_unit_id: str = field(default_factory=lambda: os.environ.get("QBL_TT_AD_UNIT_ID", ""))
    wx_ad_unit_id: str = field(default_factory=lambda: os.environ.get("QBL_WX_AD_UNIT_ID", ""))

    max_images: int = 3
    max_image_mb: int = 10

    # ---- 识别引擎 ----
    # rapidocr / sidecar。主启动预热与 OCR 适配器工厂都读这个字段
    # （engine_runner._get_ocr_adapter 用 getattr 兜底，但这里有字段更明确）。
    ocr_backend: str = field(default_factory=lambda: os.environ.get("QBL_OCR_BACKEND", "rapidocr").strip().lower())

    # ---- 内容安全（第 2 关：接微信真实接口）----    # off / wechat / local。默认 local（本地粗检桩）。
    # wechat：调 msgSecCheck（文本）+ mediaCheckAsync（图片）；失败降级放行并记录，不阻塞主流程。
    content_safety: str = field(default_factory=lambda: os.environ.get("QBL_CONTENT_SAFETY", "local").strip().lower())
    # 图片异步检测需要一个可公网访问的 URL 前缀（云托管/对象存储域名）；空则跳过图片检测并记 degraded
    content_safety_media_base: str = field(
        default_factory=lambda: os.environ.get("QBL_CONTENT_SAFETY_MEDIA_BASE", "").strip()
    )
    content_safety_timeout: float = field(default_factory=lambda: _env_float("QBL_CONTENT_SAFETY_TIMEOUT", 8.0))

    # ---- 开发兜底开关 ----
    # 原型期旁路（API 直接传 ocr_text）：生产环境必须关闭。
    # 规则：QBL_ENV=prod 下无论这个开关怎么设，一律拒绝 ocr_text；dev 下由本开关控制（默认开）。
    dev_bypass: bool = field(default_factory=lambda: os.environ.get("QBL_DEV_BYPASS", "1") == "1")

    # ---- 运行环境 ----
    env: str = field(default_factory=lambda: os.environ.get("QBL_ENV", "dev").strip().lower())

    @property
    def is_production(self) -> bool:
        return self.env in ("prod", "production", "生产")

    def default_secrets_in_use(self) -> list[str]:
        """返回仍在用默认口令的配置项名（空列表表示安全）。"""
        leaked = []
        for name, default in DEFAULT_SECRETS.items():
            value = str(getattr(self, name) or "").strip()
            # 空值也算没配：生产环境拿空口令等于没有鉴权，同样必须拒启
            if not value or value == default:
                leaked.append(name)
        return leaked

    def assert_production_ready(self) -> None:
        """生产环境自检：带着默认口令/开发通道禁止启动。"""
        if not self.is_production:
            return
        leaked = self.default_secrets_in_use()
        if leaked:
            raise InsecureProductionConfig(
                "生产环境（QBL_ENV=prod）检测到未配置或仍为默认口令："
                + "、".join(leaked)
                + "。请通过安全卡片注入 QBL_ADMIN_TOKEN / QBL_TOKEN_SECRET / QBL_PAY_SECRET 后重启。"
            )
        if self.dev_mode:
            raise InsecureProductionConfig(
                "生产环境（QBL_ENV=prod）不允许开启开发登录通道（QBL_DEV_MODE=1），请改为 0。"
            )


def get_settings() -> Settings:
    return Settings()
