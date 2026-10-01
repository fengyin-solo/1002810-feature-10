"""水体养护接口回归测试：覆盖数据同源、净化流转、并发占用、跳级与重复保存。"""
from __future__ import annotations

import warnings

import pytest
from fastapi.testclient import TestClient

warnings.filterwarnings("ignore")

from app.main import app  # noqa: E402
from app.store import store  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    """内存仓库是全局单例，每例测试前重置，避免用例之间相互污染。"""
    store.reset()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_list_and_detail_share_same_source(client: TestClient) -> None:
    """列表页与详情页读到的水质等级、版本必须是同一份数据。"""
    listed = client.get("/api/waterbody").json()["items"]
    target = next(row for row in listed if row["水体编号"] == "WATE-0003")
    detail = client.get(f"/api/waterbody/{target['id']}").json()
    assert detail["水质等级"] == target["水质等级"] == "劣Ⅴ类"
    assert detail["富营养化"] == target["富营养化"] == "重度富营养"
    assert detail["version"] == target["version"]
    # 中文展示字段与英文统计键已经对齐。
    assert detail["水体状态"] == detail["status"] == "重度污染"


def test_export_route_not_shadowed(client: TestClient) -> None:
    """/export 不能被 /{entry_id} 拦截成 422。"""
    resp = client.get("/api/waterbody/export")
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


def test_purify_moves_heavily_polluted_to_purifying_and_keeps_eutrophy(client: TestClient) -> None:
    """净化处理：重度污染 -> 净化中，富营养化程度保留旧值不回退。"""
    before = client.get("/api/waterbody/3").json()
    resp = client.post(
        "/api/waterbody/3/actions",
        json={"action": "净化处理", "expected_version": before["version"]},
    )
    assert resp.status_code == 200
    entry = resp.json()["entry"]
    assert entry["水体状态"] == "净化中"
    assert entry["富营养化"] == before["富营养化"] == "重度富营养"
    # 列表页立即读到同一份。
    after = client.get("/api/waterbody/3").json()
    assert after["水体状态"] == "净化中"


def test_purify_only_allowed_when_heavily_polluted(client: TestClient) -> None:
    """良好水体不能直接净化处理。"""
    resp = client.post(
        "/api/waterbody/1/actions",
        json={"action": "净化处理", "expected_version": 1},
    )
    assert resp.json()["ok"] is False
    assert "不能执行" in resp.json()["message"]


def test_stale_action_version_is_rejected(client: TestClient) -> None:
    """两人前后脚：后到一次动作提交因版本不符被 409 拒绝。"""
    client.post(
        "/api/waterbody/3/actions",
        json={"action": "净化处理", "expected_version": 5},
    )
    stale = client.post(
        "/api/waterbody/3/actions",
        json={"action": "验收净化", "expected_version": 5},
    )
    assert stale.status_code == 409
    assert "已被他人改动" in stale.json()["detail"]


def test_quality_grade_cannot_skip_levels(client: TestClient) -> None:
    """水质等级不许跳级，并在错误里说明可选相邻等级。"""
    resp = client.put(
        "/api/waterbody/1",
        json={"values": {"水质等级": "劣Ⅴ类"}, "expected_version": 1, "reason": "测试"},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "不允许" in detail and "一次只能调整一级" in detail


def test_grade_change_requires_reason(client: TestClient) -> None:
    """调整水质等级必须填写变更原因。"""
    resp = client.put(
        "/api/waterbody/1",
        json={"values": {"水质等级": "Ⅲ类"}, "expected_version": 1},
    )
    assert resp.status_code == 400
    assert "变更原因" in resp.json()["detail"]


def test_save_persists_after_refresh(client: TestClient) -> None:
    """保存后重新读取（退出再进来）仍是刚填的等级，且历史记录了原因。"""
    resp = client.put(
        "/api/waterbody/1",
        json={
            "values": {"水质等级": "Ⅲ类", "富营养化": "轻度富营养"},
            "expected_version": 1,
            "reason": "雨后周边面源污染汇入",
        },
    )
    assert resp.status_code == 200
    again = client.get("/api/waterbody/1").json()
    assert again["水质等级"] == "Ⅲ类"
    assert again["富营养化"] == "轻度富营养"
    assert again["history"][-1]["to"] == "Ⅲ类"
    assert again["history"][-1]["reason"] == "雨后周边面源污染汇入"


def test_duplicate_save_only_first_counts(client: TestClient) -> None:
    """同一片水体重复保存完全相同的内容，只认第一次，第二次 409。"""
    payload = {
        "values": {
            "水体类型": "景观湖",
            "水体面积": "12000",
            "换水周期": "30天",
            "管护人员": "周文",
            "水质等级": "Ⅲ类",
            "富营养化": "中营养",
        },
        "expected_version": 1,
        "reason": "第一次调整",
    }
    first = client.put("/api/waterbody/1", json=payload)
    assert first.status_code == 200
    new_version = first.json()["entry"]["version"]
    payload["expected_version"] = new_version
    second = client.put("/api/waterbody/1", json=payload)
    assert second.status_code == 409
    assert "重复保存只认第一次" in second.json()["detail"]


def test_concurrent_saves_second_rejected_then_refresh_succeeds(client: TestClient) -> None:
    """两人各持 v1：先到成功，后到 409；后者刷新拿新版本后可继续保存。"""
    first = client.put(
        "/api/waterbody/1",
        json={"values": {"水质等级": "Ⅲ类"}, "expected_version": 1, "reason": "甲先改"},
    )
    assert first.status_code == 200
    late = client.put(
        "/api/waterbody/1",
        json={"values": {"水质等级": "Ⅳ类"}, "expected_version": 1, "reason": "乙后改"},
    )
    assert late.status_code == 409
    latest = client.get("/api/waterbody/1").json()
    retried = client.put(
        "/api/waterbody/1",
        json={
            "values": {"水质等级": "Ⅳ类"},
            "expected_version": latest["version"],
            "reason": "乙刷新后相邻调整",
        },
    )
    assert retried.status_code == 200
    assert retried.json()["entry"]["水质等级"] == "Ⅳ类"


def test_grade_overview_uses_same_source(client: TestClient) -> None:
    """工作台水质等级分布与列表同源。"""
    overview = client.get("/api/waterbody/grade-overview").json()
    rows = client.get("/api/waterbody").json()["items"]
    assert overview["total"] == len(rows)
    assert overview["quality_grades"]["劣Ⅴ类"] == 1
    assert overview["statuses"]["重度污染"] == 1
