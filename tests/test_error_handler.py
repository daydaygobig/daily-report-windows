"""领域异常 → HTTP 响应的线上格式守线测试。

历史行为：HTTPException(detail={"code": ..., "message": ...})，响应体为 {"detail": {...}}。
全局 AppError 处理器必须产出完全相同的结构，前端解析才不受影响。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

# 不使用 with（避免触发 startup 事件启动调度器），仅验证路由与异常处理
client = TestClient(app)


def test_not_found_error_keeps_legacy_wire_format():
    resp = client.put("/api/models/999999999", json={"name": "不存在的模型"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == 404
    assert "不存在" in body["detail"]["message"]


def test_app_error_defaults_to_400_code_1():
    resp = client.post("/api/models/test-connection", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["code"] == 1
    assert body["detail"]["message"] == "未提供 API Key"


def test_ima_style_code_400_override():
    resp = client.delete("/api/ima/accounts/999999999")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["code"] == 400
