"""水体养护接口：维护水体，覆盖登记、保存、记录污染、净化处理、验收净化等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.waterbody import (
    ACTION_TRANSITIONS,
    WaterbodyService,
)

router = APIRouter(prefix="/api/waterbody", tags=["水体养护"])

service = WaterbodyService()

LIST_FIELDS = ["水体编号", "水体类型", "水体面积", "水质等级", "富营养化", "换水周期", "管护人员", "水体状态"]


class SavePayload(BaseModel):
    """保存水体时提交的字段：业务值 + 乐观锁版本 + 变更原因。"""

    values: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = None
    reason: str | None = None
    operator: str = "值班管理员"


class ActionPayload(BaseModel):
    """执行流转动作时携带乐观锁版本，避免后到的一次把先到的结果顶掉。"""

    action: str
    expected_version: int | None = None
    operator: str = "值班管理员"


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按水体编号检索"),
    status: str | None = Query(default=None, description="良好、轻度污染、重度污染、净化中、已净化"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按水体编号与状态过滤水体养护列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export 必须写在 /{entry_id} 之前，否则会被整型路径参数拦截成 422。
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出水体养护清单：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "waterbody", "total": total, "items": items}


@router.get("/grade-overview")
def grade_overview() -> dict[str, Any]:
    """工作台水质等级分布：与列表、详情共用同一份底层数据。"""
    return service.grade_overview()


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条水体明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"水体 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条水体，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="水体已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def save_entry(entry_id: int, payload: SavePayload) -> ActionResult:
    """保存水体业务字段。

    - expected_version 与服务端不一致时返回 409（已被他人占用），拒绝覆盖；
    - 水质等级一次只能调整一级，且调整必须填写变更原因；
    - 内容与上次保存完全相同时返回 409，重复保存只认第一次。
    """
    entry = service.save_entry(
        entry_id,
        payload.values,
        expected_version=payload.expected_version,
        reason=payload.reason,
        operator=payload.operator,
    )
    return ActionResult(ok=True, message="水体信息已保存，刷新后仍为最新值", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    """对单条水体执行记录污染、净化处理、验收净化；不允许的动作会被拦下并说明原因。"""
    action = (payload.action or "").strip()
    if action not in ACTION_TRANSITIONS:
        return ActionResult(ok=False, message=f"动作「{action}」不属于水体养护可执行范围")
    entry, message = service.run_action(
        entry_id,
        action,
        expected_version=payload.expected_version,
        operator=payload.operator,
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
