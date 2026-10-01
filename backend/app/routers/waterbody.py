"""水体养护接口：维护水体，覆盖记录污染、净化处理、验收净化等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.waterbody import WORKFLOW_STATUSES, WaterbodyService

router = APIRouter(prefix="/api/waterbody", tags=["水体养护"])

service = WaterbodyService()

LIST_FIELDS = ["水体编号", "水体类型", "水体面积", "水质等级", "富营养化", "换水周期", "管护人员", "水体状态"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按水体编号检索"),
    status_filter: str | None = Query(default=None, alias="status", description="良好、轻度污染、重度污染、净化中、已净化"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按水体编号与状态过滤水体养护列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status_filter and status_filter not in WORKFLOW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"水体状态「{status_filter}」不在允许范围：{'、'.join(WORKFLOW_STATUSES)}",
        )
    items, total = service.list_entries(keyword=keyword, status=status_filter, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出水体养护清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "waterbody", "total": total, "items": items}


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
    operator = str(payload.values.pop("operator", "") or "") if isinstance(payload.values, dict) else ""
    entry, missing = service.create_entry(payload.values, operator=operator)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="水体已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def save_entry(entry_id: int, payload: EntryPayload, response: Response) -> ActionResult:
    """保存水质登记结果：水质等级只能逐级变更且必须说明原因；
    版本号过期说明已被别人占用，返回 409 拒绝后写覆盖。"""
    operator = str(payload.values.pop("operator", "") or "") if isinstance(payload.values, dict) else ""
    version = payload.values.pop("version", None) if isinstance(payload.values, dict) else None
    entry, message, conflict = service.save_entry(
        entry_id, payload.values, version=version, operator=operator, reason=payload.remark or ""
    )
    if conflict:
        response.status_code = status.HTTP_409_CONFLICT
        return ActionResult(ok=False, message=message, entry=entry)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload, response: Response) -> ActionResult:
    """对单条水体执行记录污染、净化处理、验收净化；不允许的动作会被拦下并说明原因。

    动作同样必须带版本号：两人前后脚操作同一片水体时，后到的一次返回 409。
    """
    action = str(payload.values.get("action") or "").strip()
    version = payload.values.get("version")
    operator = str(payload.values.get("operator") or "")
    entry, message, conflict = service.run_action(
        entry_id, action, version=version, operator=operator, remark=payload.remark or ""
    )
    if conflict:
        response.status_code = status.HTTP_409_CONFLICT
        return ActionResult(ok=False, message=message, entry=entry)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
