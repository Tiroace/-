"""云托管云调用令牌：免 AppSecret 调内容安全（官方依据见 cloudbase_safety.py 文件头）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.adapters import cloudbase_safety as cb


def test_令牌读不到时降级放行不阻塞(monkeypatch):
    adapter = cb.CloudbaseTokenSafety(token_reader=lambda: "")
    result = adapter.check_text("招聘岗位：客服\n薪资 6000")
    assert result.degraded or result.code == "degraded"
    assert result.passed is True, "读不到令牌不能拦住用户"
    assert result.suggest == "pass"
    assert "云托管令牌" in result.reason


def test_令牌可用时调用成功并解析suggest(monkeypatch):
    seen = {}

    def fake_post(url, payload, timeout=8.0):
        seen["url"] = url
        seen["payload"] = payload
        return {"errcode": 0, "result": {"suggest": "pass", "label": 100}}

    monkeypatch.setattr(cb, "_post_json", fake_post)
    adapter = cb.CloudbaseTokenSafety(token_reader=lambda: "TOKEN_ABC")
    result = adapter.check_text("招聘岗位：客服")
    assert result.code == "pass"
    assert result.suggest == "pass"
    # 官方要求：令牌放在 cloudbase_access_token 参数上，不是 access_token
    assert "cloudbase_access_token=TOKEN_ABC" in seen["url"]
    assert "access_token=" not in seen["url"].replace("cloudbase_access_token=", "")
    assert seen["payload"]["version"] == 2


def test_返回risky时拦截(monkeypatch):
    monkeypatch.setattr(
        cb, "_post_json", lambda url, payload, timeout=8.0: {"errcode": 0, "result": {"suggest": "risky"}}
    )
    adapter = cb.CloudbaseTokenSafety(token_reader=lambda: "TOKEN")
    result = adapter.check_text("违规内容")
    assert result.suggest == "risky"
    assert result.passed is False


def test_未配白名单时给出可操作提示(monkeypatch):
    """48001/API unauthorized 基本都是没加白名单，提示要能直接指导运维去控制台配。"""
    monkeypatch.setattr(
        cb,
        "_post_json",
        lambda url, payload, timeout=8.0: {"errcode": 48001, "errmsg": "api unauthorized"},
    )
    adapter = cb.CloudbaseTokenSafety(token_reader=lambda: "TOKEN")
    result = adapter.check_text("测试文本")
    assert result.code == "degraded"
    assert result.passed is True
    assert "白名单" in result.reason


def test_网络异常也降级不抛(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(cb, "_post_json", boom)
    adapter = cb.CloudbaseTokenSafety(token_reader=lambda: "TOKEN")
    result = adapter.check_text("测试文本")
    assert result.code == "degraded"
    assert result.passed is True


def test_图片检测不假装已检():
    adapter = cb.CloudbaseTokenSafety(token_reader=lambda: "TOKEN")
    result = adapter.check([Path("a.png")])
    assert result.passed is True
    assert result.code == "degraded", "异步图片检测没启用就不能报通过"
    assert "media_check_async" in result.reason


def test_从官方挂载路径读令牌(tmp_path):
    token_file = tmp_path / "cloudbase_access_token"
    token_file.write_text("REAL_TOKEN\n", encoding="utf-8")
    assert cb.read_cloudbase_token(token_file) == "REAL_TOKEN"
    assert cb.read_cloudbase_token(tmp_path / "missing") == ""


def test_工厂按配置选适配器(monkeypatch):
    from backend.app.config import Settings
    from backend.app.content_safety_factory import build_content_safety

    monkeypatch.setenv("QBL_CONTENT_SAFETY", "cloudbase")
    monkeypatch.setattr(cb, "read_cloudbase_token", lambda path=None: "")
    # 工厂内部 import 的是模块内函数，这里直接验证强模式仍返回云调用适配器
    adapter = build_content_safety(Settings())
    assert adapter.name == "cloudbase-token"
