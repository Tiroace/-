"""第 0 关：生产环境用默认口令必须拒绝启动。

这条是上线硬门槛，不能只靠「记得换」——代码层面必须拦得住。
"""
from __future__ import annotations

import pytest

from backend.app.config import DEFAULT_SECRETS, InsecureProductionConfig, Settings


def _settings(monkeypatch, env: str, **secrets) -> Settings:
    monkeypatch.setenv("QBL_ENV", env)
    for name, value in secrets.items():
        if value is None:
            monkeypatch.delenv(name.upper(), raising=False)
        else:
            monkeypatch.setenv(name.upper(), value)
    return Settings()


def test_开发环境允许默认口令(monkeypatch):
    for name in ("QBL_ADMIN_TOKEN", "QBL_TOKEN_SECRET", "QBL_PAY_SECRET", "QBL_DEV_MODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("QBL_ENV", "dev")
    s = Settings()
    assert not s.is_production
    s.assert_production_ready()  # 不应抛异常


def test_生产环境用默认口令必须拒启(monkeypatch):
    for name in ("QBL_ADMIN_TOKEN", "QBL_TOKEN_SECRET", "QBL_PAY_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("QBL_DEV_MODE", raising=False)
    monkeypatch.setenv("QBL_ENV", "prod")
    s = Settings()
    assert s.is_production
    assert set(s.default_secrets_in_use()) == set(DEFAULT_SECRETS)
    with pytest.raises(InsecureProductionConfig) as exc:
        s.assert_production_ready()
    msg = str(exc.value)
    # 报错信息必须点出是哪几项没配，否则运维不知道改什么
    for name in DEFAULT_SECRETS:
        assert name in msg, f"报错里没有提到 {name}"


def test_生产环境只换一半口令也要拒启(monkeypatch):
    monkeypatch.delenv("QBL_DEV_MODE", raising=False)
    monkeypatch.setenv("QBL_ENV", "prod")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "real-admin-token-from-secret-card")
    monkeypatch.setenv("QBL_TOKEN_SECRET", "real-token-secret-from-secret-card")
    monkeypatch.delenv("QBL_PAY_SECRET", raising=False)
    s = Settings()
    assert s.default_secrets_in_use() == ["pay_secret"]
    with pytest.raises(InsecureProductionConfig):
        s.assert_production_ready()


def test_生产环境口令齐全才放行(monkeypatch):
    monkeypatch.delenv("QBL_DEV_MODE", raising=False)
    monkeypatch.setenv("QBL_ENV", "prod")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "real-admin-token-from-secret-card")
    monkeypatch.setenv("QBL_TOKEN_SECRET", "real-token-secret-from-secret-card")
    monkeypatch.setenv("QBL_PAY_SECRET", "real-pay-secret-from-secret-card")
    s = Settings()
    assert s.default_secrets_in_use() == []
    s.assert_production_ready()  # 不应抛异常


def test_生产环境不允许开开发登录通道(monkeypatch):
    monkeypatch.setenv("QBL_ENV", "prod")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "real-admin-token-from-secret-card")
    monkeypatch.setenv("QBL_TOKEN_SECRET", "real-token-secret-from-secret-card")
    monkeypatch.setenv("QBL_PAY_SECRET", "real-pay-secret-from-secret-card")
    monkeypatch.setenv("QBL_DEV_MODE", "1")
    s = Settings()
    with pytest.raises(InsecureProductionConfig) as exc:
        s.assert_production_ready()
    assert "DEV_MODE" in str(exc.value)


def test_启动钩子会调用生产自检(monkeypatch):
    """startup 必须真的调 assert_production_ready，而不是只定义了个方法没人用。"""
    import inspect

    from backend.app import main

    src = inspect.getsource(main._startup)
    assert "assert_production_ready" in src, "startup 没有调用生产自检，默认口令能带着上线"
