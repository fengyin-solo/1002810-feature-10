"""水体养护业务规则：保存、状态流转、并发占用与水质等级跳级校验都收在这里。

数据口径（列表页、详情页、工作台必须读同一份）：
- 业务字段统一用中文名：水体编号/水体类型/水体面积/水质等级/富营养化/换水周期/管护人员/水体状态。
- status/pending/abnormal 仍保留为英文键，供运营概览等通用页面统计，不作为业务展示来源。
- version 是乐观锁版本号：每次保存或执行动作都 +1，提交时必须带上进入页面时读到的版本。
- fingerprint 记录当前业务字段的内容指纹：同一片水体再次提交且内容完全相同，只认第一次。
- history 记录水质等级的每次变更，便于详情页说明"为什么改、谁改的"。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.store import store

MODULE = "waterbody"
REQUIRED_FIELDS = ["水体编号", "水体类型", "水体面积"]

# 水质等级：按国标地表水由好到坏排列，索引差大于 1 即视为跳级。
QUALITY_GRADES = ["Ⅰ类", "Ⅱ类", "Ⅲ类", "Ⅳ类", "Ⅴ类", "劣Ⅴ类"]
# 富营养化程度：由轻到重，净化处理不会改动它，由保存动作显式维护。
EUTROPHY_LEVELS = ["无", "贫营养", "中营养", "轻度富营养", "中度富营养", "重度富营养"]
# 水体状态（流转机）。
STATUS_ORDER = ["良好", "轻度污染", "重度污染", "净化中", "已净化"]
DEFAULT_STATUS = STATUS_ORDER[0]

# 每个动作允许的"当前状态 -> 目标状态"流转；净化处理针对的是重度污染水体。
ACTION_TRANSITIONS: dict[str, dict[str, str]] = {
    "记录污染": {"良好": "轻度污染", "轻度污染": "重度污染"},
    "净化处理": {"重度污染": "净化中"},
    "验收净化": {"净化中": "已净化"},
}

# 保存时允许修改的业务字段（指纹与类型清洗也只针对这些字段）。
EDITABLE_FIELDS = ["水体类型", "水体面积", "换水周期", "管护人员", "水质等级", "富营养化"]

# 模块内一把锁：内存仓库下保证"读-校验-写"原子，两人前后脚提交时第二个会因版本不符被拒。
_lock = threading.RLock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value: Any) -> str:
    """统一清洗成去空白的字符串，保证指纹比较不受类型/空格影响。"""
    if value is None:
        return ""
    return str(value).strip()


def _fingerprint(values: dict[str, Any]) -> str:
    return "|".join(_clean(values.get(field)) for field in EDITABLE_FIELDS)


class WaterbodyService:
    # ---- 读取：列表与详情都经过 _normalize，保证读到的是同一份规范化数据 ----
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        with _lock:
            rows = [self._normalize(dict(row)) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("水体编号", ""))]
        if status:
            rows = [row for row in rows if row.get("水体状态") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        with _lock:
            row = store.find(MODULE, entry_id)
            return self._normalize(dict(row)) if row is not None else None

    # ---- 登记 ----
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _clean(values.get(field))]
        if missing:
            return None, missing
        with _lock:
            rows = store.rows(MODULE)
            entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            entry["水体编号"] = _clean(values.get("水体编号"))
            entry["水体类型"] = _clean(values.get("水体类型"))
            entry["水体面积"] = _clean(values.get("水体面积"))
            entry["换水周期"] = _clean(values.get("换水周期"))
            entry["管护人员"] = _clean(values.get("管护人员"))
            entry["水质等级"] = QUALITY_GRADES[0]
            entry["富营养化"] = EUTROPHY_LEVELS[0]
            entry["水体状态"] = DEFAULT_STATUS
            entry["version"] = 1
            entry["fingerprint"] = _fingerprint(entry)
            entry["history"] = []
            entry["updated_at"] = _now()
            self._sync_flags(entry)
            rows.append(entry)
            return dict(entry), []

    # ---- 保存：版本占用校验 + 跳级校验 + 重复保存只认第一次 ----
    def save_entry(
        self,
        entry_id: int,
        values: dict[str, Any],
        *,
        expected_version: int | None = None,
        reason: str | None = None,
        operator: str = "值班管理员",
    ) -> dict[str, Any]:
        with _lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                raise HTTPException(status_code=404, detail=f"水体 {entry_id} 不存在或已归档")
            self._normalize(entry)

            current_version = int(entry.get("version", 1))
            if expected_version is not None and int(expected_version) != current_version:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"该水体已被他人改动（当前版本 v{current_version}，你打开时是 v{expected_version}），"
                        "本次保存已拒绝，请刷新后基于最新数据再改，以免覆盖他人结果。"
                    ),
                )

            new_values = {field: _clean(values.get(field)) for field in EDITABLE_FIELDS}

            grade = new_values["水质等级"]
            old_grade = _clean(entry.get("水质等级"))
            if grade and grade not in QUALITY_GRADES:
                raise HTTPException(
                    status_code=400, detail=f"水质等级「{grade}」不在允许范围：{'、'.join(QUALITY_GRADES)}"
                )
            if grade and grade != old_grade:
                old_idx = QUALITY_GRADES.index(old_grade) if old_grade in QUALITY_GRADES else 0
                new_idx = QUALITY_GRADES.index(grade)
                if abs(new_idx - old_idx) > 1:
                    neighbors = self._neighbors(old_grade)
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"水质等级不允许从「{old_grade}」直接跳到「{grade}」（一次只能调整一级）。"
                            f"本次可选：{'、'.join(neighbors)}；请分阶段多次登记并在变更原因里说明依据。"
                        ),
                    )
                if not _clean(reason):
                    raise HTTPException(
                        status_code=400, detail="调整水质等级必须填写变更原因，说明依据后再保存。"
                    )

            eutrophy = new_values["富营养化"]
            if eutrophy and eutrophy not in EUTROPHY_LEVELS:
                raise HTTPException(
                    status_code=400,
                    detail=f"富营养化程度「{eutrophy}」不在允许范围：{'、'.join(EUTROPHY_LEVELS)}",
                )

            # 空字符串表示本次不改该字段：以旧值兜底后再算指纹。
            merged = {
                field: (new_values[field] or _clean(entry.get(field)))
                for field in EDITABLE_FIELDS
            }
            next_fingerprint = _fingerprint(merged)
            if next_fingerprint == _clean(entry.get("fingerprint")):
                raise HTTPException(
                    status_code=409,
                    detail="内容与上一次保存完全相同，同一片水体重复保存只认第一次，本次未重复写入。",
                )

            for field in EDITABLE_FIELDS:
                entry[field] = merged[field]

            if grade and grade != old_grade:
                entry.setdefault("history", []).append({
                    "from": old_grade,
                    "to": grade,
                    "reason": _clean(reason),
                    "operator": _clean(operator) or "值班管理员",
                    "at": _now(),
                })

            entry["version"] = current_version + 1
            entry["fingerprint"] = next_fingerprint
            entry["updated_at"] = _now()
            return self._normalize(dict(entry))

    # ---- 动作：记录污染 / 净化处理 / 验收净化，同样受版本与流转规则约束 ----
    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        expected_version: int | None = None,
        operator: str = "值班管理员",
    ) -> tuple[dict[str, Any] | None, str]:
        with _lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"水体 {entry_id} 不存在或已归档"
            self._normalize(entry)

            transitions = ACTION_TRANSITIONS.get(action)
            if transitions is None:
                return None, f"动作「{action}」不属于水体养护可执行范围"

            current_version = int(entry.get("version", 1))
            if expected_version is not None and int(expected_version) != current_version:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"该水体已被他人改动（当前版本 v{current_version}，你打开时是 v{expected_version}），"
                        f"「{action}」已拒绝，请刷新后再操作。"
                    ),
                )

            current_status = _clean(entry.get("水体状态"))
            target = transitions.get(current_status)
            if target is None:
                allowed = [state for state, to in transitions.items()]
                tip = f"，当前为「{current_status}」，仅 {'、'.join(allowed)} 状态可执行" if allowed else ""
                return None, f"水体当前状态不能执行「{action}」{tip}"

            entry["水体状态"] = target
            entry["version"] = current_version + 1
            entry["updated_at"] = _now()
            self._sync_flags(entry)
            return self._normalize(dict(entry)), f"水体已{action}，状态更新为「{target}」"

    # ---- 工作台：水质等级分布与状态分布，数据同样来自这里（与详情同一份） ----
    def grade_overview(self) -> dict[str, Any]:
        with _lock:
            rows = [self._normalize(dict(row)) for row in store.rows(MODULE)]
        grade_counts = {grade: 0 for grade in QUALITY_GRADES}
        status_counts = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            grade = _clean(row.get("水质等级"))
            if grade in grade_counts:
                grade_counts[grade] += 1
            state = _clean(row.get("水体状态"))
            if state in status_counts:
                status_counts[state] += 1
        return {
            "total": len(rows),
            "quality_grades": grade_counts,
            "statuses": status_counts,
        }

    # ---- 内部工具 ----
    def _neighbors(self, grade: str) -> list[str]:
        if grade not in QUALITY_GRADES:
            return [QUALITY_GRADES[0]]
        idx = QUALITY_GRADES.index(grade)
        return [QUALITY_GRADES[i] for i in (idx - 1, idx + 1) if 0 <= i < len(QUALITY_GRADES)]

    def _normalize(self, entry: dict[str, Any]) -> dict[str, Any]:
        """把一条记录补齐为统一口径，并让英文键与中文业务字段保持同步。"""
        entry.setdefault("水质等级", QUALITY_GRADES[0])
        entry.setdefault("富营养化", EUTROPHY_LEVELS[0])
        # 历史脏数据可能只写了英文 status，用它回填中文水体状态。
        if not _clean(entry.get("水体状态")) and _clean(entry.get("status")) in STATUS_ORDER:
            entry["水体状态"] = _clean(entry.get("status"))
        entry.setdefault("水体状态", DEFAULT_STATUS)
        for field in EDITABLE_FIELDS:
            entry.setdefault(field, "")
        entry.setdefault("version", 1)
        entry.setdefault("history", [])
        entry.setdefault("updated_at", _now())
        if not _clean(entry.get("fingerprint")):
            entry["fingerprint"] = _fingerprint(entry)
        self._sync_flags(entry)
        return entry

    def _sync_flags(self, entry: dict[str, Any]) -> None:
        state = _clean(entry.get("水体状态")) or DEFAULT_STATUS
        # 通用运营概览按英文 status/pending/abnormal 统计，这里与水体状态对齐。
        entry["status"] = state
        entry["pending"] = state != "已净化"
        entry["abnormal"] = state in ("轻度污染", "重度污染", "净化中")
