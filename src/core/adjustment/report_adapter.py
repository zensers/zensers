"""桥接: session dict → v2 Report 接口"""

from types import SimpleNamespace
from typing import Any, Dict, List


class SessionReportAdapter:
    """包装 session dict, 使 v2 执行器可读写"""

    def __init__(self, session: dict):
        self._session = session
        self.id = session.get("session_id", "unknown")
        self._version = session.get("_report_version", 0)

    @property
    def version(self) -> int:
        return self._version

    def increment_version(self):
        self._version += 1
        self._session["_report_version"] = self._version

    @property
    def sections(self) -> List[SimpleNamespace]:
        """v2 _build_tree 用 getattr 访问字段, 必须返回类对象"""
        research = self._session.get("research_result", {})
        report = research.get("report", {})
        raw = report.get("sections", [])
        return [self._to_obj(s) for s in raw]

    @sections.setter
    def sections(self, value: List[Any]) -> None:
        """v2 sync_to_report(report) 设置 sections 时写回 session"""
        research = self._session.setdefault("research_result", {})
        research.setdefault("report", {})["sections"] = [
            self._to_dict(s) for s in value
        ]
        self.increment_version()

    def to_dict(self) -> Dict:
        """SnapshotManager._serialize 用 json.dumps(report), 必须返回纯 dict"""
        research = self._session.get("research_result", {})
        report = research.get("report", {})
        return {
            "id": self.id,
            "sections": report.get("sections", []),
            "_version": self._version,
        }

    def restore_from_dict(self, data: dict) -> None:
        """从快照 dict 恢复 session 中的报告数据"""
        report = self._session.setdefault("research_result", {}).setdefault("report", {})
        report["sections"] = data.get("sections", [])
        self._version = data.get("_version", 0)
        self._session["_report_version"] = self._version

    @staticmethod
    def _to_obj(d: dict) -> SimpleNamespace:
        obj = SimpleNamespace()
        for k, v in d.items():
            if isinstance(v, dict):
                setattr(obj, k, SessionReportAdapter._to_obj(v))
            elif isinstance(v, list):
                setattr(obj, k, [
                    SessionReportAdapter._to_obj(i) if isinstance(i, dict) else i
                    for i in v
                ])
            else:
                setattr(obj, k, v)
        return obj

    @staticmethod
    def _to_dict(o: Any) -> Any:
        if isinstance(o, SimpleNamespace):
            return {k: SessionReportAdapter._to_dict(v) for k, v in o.__dict__.items()}
        if isinstance(o, list):
            return [SessionReportAdapter._to_dict(v) for v in o]
        return o
