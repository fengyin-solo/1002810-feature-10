"""水体养护业务规则：水质等级流转、乐观锁并发控制与字段校验都收在这里。

列表页与详情页都从 store 的同一条记录取值，任何保存/动作都必须带版本号；
版本号对不上说明这片水体已被别人抢先保存，本次提交直接拒绝。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "waterbody"
REQUIRED_FIELDS = ["水体编号", "水体类型", "水体面积"]
EDITABLE_FIELDS = ["水质等级", "富营养化", "换水周期", "管护人员"]

# 水质等级序列：只能在相邻两级之间变更，禁止跳级
WATER_GRADES = ["良好", "轻度污染", "重度污染"]
POLLUTED_GRADES = {"轻度污染", "重度污染"}
# 富营养化程度序列：净化一次只允许好转一级
EUTRO_LEVELS = ["无", "轻度", "中度", "重度"]
# 水体业务状态：内部 status 与列表「水体状态」列始终写同一份值
WORKFLOW_STATUSES = ["良好", "轻度污染", "重度污染", "净化中", "已净化"]
ACTION_NAMES = ["记录污染", "净化处理", "验收净化"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _grade_index(grade: str) -> int:
    return WATER_GRADES.index(grade)


def _eutro_index(level: str) -> int:
    return EUTRO_LEVELS.index(level)


def _is_pending(status: str) -> bool:
    return status in {"轻度污染", "重度污染", "净化中"}


class WaterbodyService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("水体编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        # 与列表页读的是 store 里的同一条记录，不存在两份数据
        return store.find(MODULE, entry_id)

    def create_entry(
        self, values: dict[str, Any], operator: str = ""
    ) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["水质等级"] = WATER_GRADES[0]
        entry["富营养化"] = EUTRO_LEVELS[0]
        entry["换水周期"] = ""
        entry["管护人员"] = operator or ""
        entry["status"] = "良好"
        entry["水体状态"] = "良好"
        entry["version"] = 1
        entry["pending"] = False
        entry["abnormal"] = False
        entry["history"] = []
        self._trace(entry, "登记水体", end="良好", operator=operator)
        rows.append(entry)
        return entry, []

    def save_entry(
        self,
        entry_id: int,
        values: dict[str, Any],
        version: Any,
        operator: str = "",
        reason: str = "",
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """保存水质登记结果。

        返回 (记录, 说明, 是否版本冲突)：冲突时记录原样返回，由接口层转成 409。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"水体 {entry_id} 不存在或已归档", False

        ok, conflict_message = self._check_version(entry, version)
        if not ok:
            return entry, conflict_message, True

        reason = str(reason or "").strip()
        updates: dict[str, Any] = {}
        old_grade = str(entry.get("水质等级", "良好"))
        old_eutro = str(entry.get("富营养化", "无"))

        new_grade = values.get("水质等级")
        if new_grade is not None and str(new_grade).strip():
            new_grade = str(new_grade).strip()
            if new_grade not in WATER_GRADES:
                return None, f"水质等级「{new_grade}」不在允许范围：{'、'.join(WATER_GRADES)}", False
            if new_grade != old_grade:
                if abs(_grade_index(new_grade) - _grade_index(old_grade)) != 1:
                    return (
                        None,
                        f"水质等级不允许从「{old_grade}」直接跳变为「{new_grade}」，"
                        "只能逐级变更，请先选择相邻等级并分两次保存",
                        False,
                    )
                if not reason:
                    return None, f"水质等级由「{old_grade}」变更为「{new_grade}」时必须填写变更原因", False
                updates["水质等级"] = new_grade

        new_eutro = values.get("富营养化")
        if new_eutro is not None and str(new_eutro).strip():
            new_eutro = str(new_eutro).strip()
            if new_eutro not in EUTRO_LEVELS:
                return None, f"富营养化程度「{new_eutro}」不在允许范围：{'、'.join(EUTRO_LEVELS)}", False
            if new_eutro != old_eutro:
                updates["富营养化"] = new_eutro

        for field in ("换水周期", "管护人员"):
            val = values.get(field)
            if val is not None and str(val).strip() and str(val).strip() != str(entry.get(field, "")):
                updates[field] = str(val).strip()

        if not updates:
            return None, "内容相对最新版本没有任何变化，无需重复保存", False

        entry.update(updates)
        if "水质等级" in updates:
            grade = str(entry["水质等级"])
            if grade in POLLUTED_GRADES:
                entry["status"] = grade
                entry["水体状态"] = grade
            elif entry.get("status") in POLLUTED_GRADES:
                entry["status"] = "良好"
                entry["水体状态"] = "良好"

        entry["version"] = int(entry.get("version", 1)) + 1
        entry["pending"] = _is_pending(str(entry.get("status", "良好")))
        entry["abnormal"] = entry.get("status") == "重度污染"
        self._trace(
            entry,
            "保存水质",
            start=old_grade if "水质等级" in updates else "—",
            end=str(entry.get("水质等级", old_grade)),
            reason=reason,
            operator=operator,
        )
        changed = "、".join(f"{name}更新为「{entry[name]}」" for name in updates)
        return entry, f"保存成功：{changed}，已生成版本 {entry['version']}，刷新后读到的仍是这份结果", False

    def run_action(
        self,
        entry_id: int,
        action: str,
        version: Any = None,
        operator: str = "",
        remark: str = "",
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """对单条水体执行记录污染、净化处理、验收净化，同样受版本号保护。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"水体 {entry_id} 不存在或已归档", False
        if action not in ACTION_NAMES:
            return None, f"动作「{action}」不属于水体养护可执行范围", False

        ok, conflict_message = self._check_version(entry, version)
        if not ok:
            return entry, conflict_message, True

        status = str(entry.get("status", "良好"))
        old_grade = str(entry.get("水质等级", "良好"))
        old_eutro = str(entry.get("富营养化", "无"))

        if action == "记录污染":
            if status == "净化中":
                return None, "水体正在净化处理中，不能再记录污染", False
            if _grade_index(old_grade) >= len(WATER_GRADES) - 1:
                return None, f"水质等级已是「{old_grade}」，不能继续变差", False
            new_grade = WATER_GRADES[_grade_index(old_grade) + 1]
            entry["水质等级"] = new_grade
            entry["status"] = new_grade
            entry["水体状态"] = new_grade
            message = f"污染已记录，水质等级由「{old_grade}」变为「{new_grade}」"

        elif action == "净化处理":
            if status not in {"轻度污染", "重度污染", "净化中"}:
                return None, f"当前水体状态为「{status}」，没有待净化的污染，无需净化处理", False
            changes: list[str] = []
            if old_grade != "良好":
                entry["水质等级"] = WATER_GRADES[_grade_index(old_grade) - 1]
                changes.append(f"水质等级「{old_grade}」→「{entry['水质等级']}」")
            if old_eutro != "无":
                entry["富营养化"] = EUTRO_LEVELS[_eutro_index(old_eutro) - 1]
                changes.append(f"富营养化「{old_eutro}」→「{entry['富营养化']}」")
            entry["status"] = "净化中"
            entry["水体状态"] = "净化中"
            if changes:
                message = "净化处理完成：" + "，".join(changes) + "；水体进入净化中，可继续净化或申请验收"
            else:
                message = "水质已恢复良好且无富营养化，请直接进行验收净化"

        else:  # 验收净化
            if status != "净化中":
                return None, f"当前水体状态为「{status}」，只有净化中的水体可以验收", False
            if str(entry.get("水质等级")) != "良好":
                return (
                    None,
                    f"水质等级仍为「{entry.get('水质等级')}」，尚未恢复到良好，"
                    "请继续净化处理后再验收",
                    False,
                )
            entry["status"] = "已净化"
            entry["水体状态"] = "已净化"
            message = "净化已验收，水体状态更新为「已净化」"

        entry["version"] = int(entry.get("version", 1)) + 1
        entry["pending"] = _is_pending(str(entry.get("status", "良好")))
        entry["abnormal"] = entry.get("status") == "重度污染"
        self._trace(
            entry,
            action,
            start=f"{old_grade}/{old_eutro}",
            end=f"{entry.get('水质等级')}/{entry.get('富营养化')}",
            reason=remark,
            operator=operator,
        )
        return entry, f"{message}（版本 {entry['version']}）", False

    def _check_version(self, entry: dict[str, Any], version: Any) -> tuple[bool, str]:
        if version is None or str(version).strip() == "":
            return False, "本次提交缺少版本号，请重新打开详情后再保存"
        try:
            submitted = int(version)
        except (TypeError, ValueError):
            return False, "版本号格式不正确，请重新打开详情后再保存"
        current = int(entry.get("version", 1))
        if submitted != current:
            return (
                False,
                f"该水体刚被别人保存过（最新版本 {current}，你打开的是版本 {submitted}），"
                "本次提交已被拒绝，请刷新取得最新数据后再改",
            )
        return True, ""

    def _trace(
        self,
        entry: dict[str, Any],
        action: str,
        *,
        start: str = "",
        end: str = "",
        reason: str = "",
        operator: str = "",
    ) -> None:
        entry.setdefault("history", []).append(
            {
                "时间": _now(),
                "操作人": operator or "值班管理员",
                "动作": action,
                "由": start,
                "至": end,
                "原因": reason or "—",
            }
        )
