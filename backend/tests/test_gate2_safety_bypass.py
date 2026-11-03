"""第 2 关：ocr_text 旁路只能在开发模式用；内容安全失败必须降级不阻塞。"""
from __future__ import annotations

import pytest

from backend.tests.conftest import auth, login


def _create_with_text(client, token, text="招聘岗位：客服\n薪资 6000 元/月"):
    return client.post("/analysis", json={"ocr_text": text}, headers=auth(token))


class TestOcrText旁路:
    def test_开发环境允许传预置文本(self, client, monkeypatch):
        monkeypatch.setenv("QBL_ENV", "dev")
        monkeypatch.setenv("QBL_DEV_BYPASS", "1")
        token = login(client)["token"]
        r = _create_with_text(client, token)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["task_id"]

    def test_开发环境显式关闭后拒绝(self, client, monkeypatch):
        monkeypatch.setenv("QBL_ENV", "dev")
        monkeypatch.setenv("QBL_DEV_BYPASS", "0")
        token = login(client)["token"]
        r = _create_with_text(client, token)
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "BYPASS_FORBIDDEN"

    def test_生产环境必须拒绝预置文本(self, client, monkeypatch):
        """生产环境无论开关怎么设，传 ocr_text 一律拒绝。"""
        monkeypatch.setenv("QBL_ENV", "prod")
        monkeypatch.setenv("QBL_DEV_BYPASS", "1")  # 就算开关开着也不行
        token = login(client)["token"]
        r = _create_with_text(client, token)
        assert r.status_code == 400, f"生产环境居然接受了预置文本：{r.status_code} {r.text[:200]}"
        assert r.json()["error"]["code"] == "BYPASS_FORBIDDEN"

    def test_生产环境multipart分支也拒绝(self, client, monkeypatch):
        monkeypatch.setenv("QBL_ENV", "prod")
        token = login(client)["token"]
        r = client.post(
            "/analysis",
            data={"ocr_text": "招聘岗位：客服"},
            headers=auth(token),
        )
        assert r.status_code == 400, f"multipart 分支漏了闸门：{r.status_code} {r.text[:200]}"
        assert r.json()["error"]["code"] == "BYPASS_FORBIDDEN"

    def test_不传预置文本时不受影响(self, client, monkeypatch):
        """闸门只挡旁路，正常传图片不受影响。"""
        monkeypatch.setenv("QBL_ENV", "prod")
        token = login(client)["token"]
        from backend.tests.conftest import upload_image

        iid = upload_image(client, token, "normal")
        r = client.post("/analysis", json={"image_ids": [iid]}, headers=auth(token))
        assert r.status_code == 200, r.text


class Test内容安全降级:
    def test_默认为本地桩且标注未配置(self, monkeypatch):
        from backend.app.config import Settings
        from backend.app.content_safety_factory import build_content_safety

        monkeypatch.delenv("QBL_CONTENT_SAFETY", raising=False)
        s = Settings()
        adapter = build_content_safety(s)
        assert adapter.name == "local-stub"

    def test_关闭时明确标注disabled不自欺(self, monkeypatch):
        from backend.app.config import Settings
        from backend.app.content_safety_factory import build_content_safety

        monkeypatch.setenv("QBL_CONTENT_SAFETY", "off")
        s = Settings()
        result = build_content_safety(s).check([])
        assert result.passed is True
        assert result.code == "disabled"

    def test_微信接口不可用时降级放行并记录(self, monkeypatch):
        """没配 AppID/Secret 时调 msgSecCheck 必须降级放行，不能阻塞用户。"""
        from engine.adapters.wechat_safety import WechatContentSafety

        safety = WechatContentSafety(appid="", secret="")
        check = safety.check_text("招聘岗位：客服")
        assert check.degraded is True, "接口不可用时应降级"
        assert check.suggest == "pass", "降级时必须放行，不能拦住用户"
        assert "未配置" in check.reason

    def test_微信网络异常时降级放行(self, monkeypatch):
        from engine.adapters.wechat_safety import WechatContentSafety

        safety = WechatContentSafety(appid="wx_test", secret="secret_test")

        def boom(*a, **k):
            raise Exception("network down")

        # tokens 是实例属性，直接在实例上替换（打类属性会 AttributeError）
        monkeypatch.setattr(safety, "tokens", type("T", (), {"get": staticmethod(boom)})())
        check = safety.check_text("招聘岗位：客服")
        assert check.degraded is True
        assert check.suggest == "pass"

    def test_微信返回risky时拦截(self, monkeypatch):
        from engine.adapters import wechat_safety

        monkeypatch.setattr(
            wechat_safety,
            "_post_json",
            lambda url, payload, timeout=8.0: {
                "errcode": 0,
                "result": {"suggest": "risky", "label": 20001},
            },
        )
        safety = wechat_safety.WechatContentSafety(appid="wx_test", secret="secret_test")
        monkeypatch.setattr(safety, "tokens", type("T", (), {"get": staticmethod(lambda: "fake-token")})())
        check = safety.check_text("违规内容")
        assert check.suggest == "risky"
        assert check.degraded is False

    def test_图片无公网地址时降级不假报通过(self, monkeypatch):
        from pathlib import Path

        from engine.adapters.wechat_safety import WechatContentSafety

        safety = WechatContentSafety(appid="wx_test", secret="secret_test", media_url_builder=None)
        result = safety.check([Path("a.png")])
        assert result.passed is True
        assert result.code == "degraded", "没有公网 URL 就不能假装图片检测过了"
