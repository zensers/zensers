"""Controlled retry policy for the final L1-L5 defense loop.

This module deliberately does not search, rewrite chapters, or mutate report
data.  It only decides whether the orchestrator may execute another repair
round after an audit result.
"""

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class DefenseLoopDecision:
    status: str
    should_repair: bool
    round_number: int
    issue_signature: Tuple[str, ...] = ()
    stages: Tuple[str, ...] = ()
    actions: Tuple[Dict[str, Any], ...] = ()
    termination_reason: str = ""
    reason: str = ""


class DefenseLoopController:
    """Bound and make auditable the audit -> repair -> re-audit cycle."""

    # Coverage is a repairable content contract, even though it is not one of
    # the evidence-defense layers.  Keeping it in the controller prevents a
    # detected missing topic/metric from being silently converted to
    # ``no_actions``.
    _STAGES = ("L1", "L2", "L3", "L4", "L5", "coverage")

    def __init__(self, max_rounds: int = 3):
        if max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        self.max_rounds = max_rounds
        self.rounds = 0
        self._previous_signature: Optional[Tuple[str, ...]] = None
        # Issue lifecycle is deliberately kept separate from the audit
        # signature.  A signature only describes the current audit result;
        # it cannot prevent A -> B -> A from scheduling A twice.
        self.issue_states: Dict[str, str] = {}
        self._processed_action_keys = set()
        self._current_issue_keys = set()
        self.action_lifecycle: List[Dict[str, Any]] = []

    @staticmethod
    def issue_key(issue: Dict[str, Any]) -> str:
        """Return a stable identity for an audit issue.

        Volatile prose and observed values are excluded so that a reworded
        audit finding remains the same lifecycle item.
        """
        if not isinstance(issue, dict):
            return "malformed|" + json.dumps(issue, ensure_ascii=False, sort_keys=True, default=str)
        return "|".join(
            str(issue.get(key, "") or "").strip()
            for key in ("layer", "code", "chapter_id", "section_id", "metric")
        )

    @staticmethod
    def _action_key(action: Dict[str, Any]) -> str:
        """Return the identity used to suppress a repeated repair action."""
        if not isinstance(action, dict):
            return "malformed|" + json.dumps(action, ensure_ascii=False, sort_keys=True, default=str)
        return "|".join(
            str(action.get(key, "") or "").strip()
            for key in ("layer", "type", "chapter_id", "section_id", "metric", "code")
        )

    def mark_actions_processed(self, actions: Tuple[Dict[str, Any], ...] | List[Dict[str, Any]]) -> None:
        """Mark attempted actions so later audit rounds cannot replay them."""
        for action in actions or []:
            if not isinstance(action, dict):
                continue
            self._processed_action_keys.add(self._action_key(action))
            self._set_action_lifecycle_status(action, "executed")
            chapter = str(action.get("chapter_id", "") or "").strip()
            metric = str(action.get("metric", "") or "").strip()
            layer = str(action.get("layer", "") or "").strip()
            # Search and structural actions have no issue code in their
            # action payload, so also retain an action-type scoped suppression
            # key.  The action type is important: one evidence supplement may
            # legitimately expose a new extraction/rewrite problem for the
            # same metric, which must not be confused with replaying the old
            # search action.
            if chapter and (metric or action.get("type") == "rewrite_scope"):
                self._processed_action_keys.add(
                    "scope|" + "|".join((layer, chapter, metric, str(action.get("type", ""))))
                )
            for issue_key in self._current_issue_keys:
                parts = issue_key.split("|")
                if len(parts) != 5:
                    continue
                issue_layer, issue_code, issue_chapter, _section, issue_metric = parts
                same_scope = (
                    issue_chapter == chapter
                    and (not metric or issue_metric == metric)
                    and (not layer or issue_layer == layer)
                )
                code_match = (
                    not action.get("code")
                    or issue_code in str(action.get("code", "")).split("+")
                )
                if same_scope and code_match:
                    self.issue_states[issue_key] = "processed_but_unresolved"

    def _set_action_lifecycle_status(self, action: Dict[str, Any], status: str) -> None:
        key = self._action_key(action)
        for item in self.action_lifecycle:
            if item.get("action_key") == key:
                item["status"] = status
                return

    def mark_actions_failed(self, actions: Tuple[Dict[str, Any], ...] | List[Dict[str, Any]]) -> None:
        """Record an action execution failure without hiding the audit issue."""
        for action in actions or []:
            if isinstance(action, dict):
                self._set_action_lifecycle_status(action, "failed")

    def finalize_action_verification(self, audit: Dict[str, Any]) -> None:
        """Mark executed actions verified or unresolved after a re-audit."""
        current_issue_keys = {
            self.issue_key(issue)
            for issue in (audit.get("issues", []) if isinstance(audit, dict) else [])
            if isinstance(issue, dict)
        }
        for item in self.action_lifecycle:
            if item.get("status") != "executed":
                continue
            action = item.get("action", {})
            action_layer = str(action.get("layer", "") or "")
            action_chapter = str(action.get("chapter_id", "") or "")
            action_metric = str(action.get("metric", "") or "")
            action_code = str(action.get("code", "") or "")
            unresolved = False
            for issue in (audit.get("issues", []) if isinstance(audit, dict) else []):
                if not isinstance(issue, dict):
                    continue
                same_scope = (
                    (not action_layer or not issue.get("layer") or str(issue.get("layer", "") or "") == action_layer)
                    and (not action_chapter or not issue.get("chapter_id") or str(issue.get("chapter_id", "") or "") == action_chapter)
                    and (not action_metric or not issue.get("metric") or str(issue.get("metric", "") or "") == action_metric)
                )
                same_code = (
                    not action_code
                    or str(issue.get("code", "") or "") == action_code
                    or str(issue.get("code", "") or "") in action_code.split("+")
                )
                if same_scope and same_code:
                    unresolved = True
                    break
            item["status"] = "unresolved" if unresolved else "verified"

    def _update_issue_states(self, audit: Dict[str, Any]) -> None:
        current = set()
        for issue in (audit.get("issues", []) if isinstance(audit, dict) else []):
            if not isinstance(issue, dict):
                continue
            key = self.issue_key(issue)
            current.add(key)
            self.issue_states.setdefault(key, "pending")
        self._current_issue_keys = current
        for key, state in list(self.issue_states.items()):
            if key not in current and state in {"pending", "processed_but_unresolved"}:
                self.issue_states[key] = "resolved"

    @staticmethod
    def _signature(audit: Dict[str, Any]) -> Tuple[str, ...]:
        issues = audit.get("issues", []) if isinstance(audit, dict) else []
        normalized = []
        for issue in issues or []:
            if not isinstance(issue, dict):
                normalized.append(json.dumps(issue, ensure_ascii=False, sort_keys=True, default=str))
                continue
            # Include only identity-bearing fields.  Volatile messages or
            # suggestion text must not make an unchanged defect look new.
            normalized.append(json.dumps({
                key: issue.get(key, "")
                for key in ("layer", "code", "chapter_id", "section_id", "metric", "value")
            }, ensure_ascii=False, sort_keys=True, default=str))
        return tuple(sorted(normalized))

    def evaluate(
        self,
        audit: Dict[str, Any],
        executable_actions: Optional[List[Dict[str, Any]]],
    ) -> DefenseLoopDecision:
        self._update_issue_states(audit)
        signature = self._signature(audit)

        if isinstance(audit, dict) and audit.get("passed") is True:
            return DefenseLoopDecision(
                status="passed",
                should_repair=False,
                round_number=self.rounds,
                issue_signature=signature,
                reason="defense audit passed",
            )

        issue_layers = {
            str(issue.get("layer", ""))
            for issue in (audit.get("issues", []) if isinstance(audit, dict) else [])
            if isinstance(issue, dict)
        }
        stages = tuple(layer for layer in self._STAGES if layer in issue_layers)
        valid_actions = [
            action for action in (executable_actions or [])
            if isinstance(action, dict)
            and str(action.get("type", "")).strip()
            and str(action.get("layer", "")).strip() in stages
            and self._action_key(action) not in self._processed_action_keys
            and "scope|" + "|".join(
                (
                    str(action.get("layer", "") or "").strip(),
                    str(action.get("chapter_id", "") or "").strip(),
                    str(action.get("metric", "") or "").strip(),
                    str(action.get("type", "") or "").strip(),
                )
            ) not in self._processed_action_keys
        ]

        for action in valid_actions:
            key = self._action_key(action)
            if not any(item.get("action_key") == key for item in self.action_lifecycle):
                self.action_lifecycle.append({
                    "action_key": key,
                    "action": dict(action),
                    "status": "planned",
                    "round": self.rounds + 1,
                })

        if self.rounds >= self.max_rounds:
            return DefenseLoopDecision(
                status="deliver_with_warnings",
                should_repair=False,
                round_number=self.rounds,
                issue_signature=signature,
                stages=stages,
                termination_reason="max_rounds",
                reason="maximum defense repair rounds reached",
            )

        if not valid_actions:
            return DefenseLoopDecision(
                status="deliver_with_warnings",
                should_repair=False,
                round_number=self.rounds,
                issue_signature=signature,
                stages=stages,
                termination_reason="no_actions",
                reason="no executable repair action was produced for the audited layers",
            )

        if self._previous_signature == signature:
            return DefenseLoopDecision(
                status="deliver_with_warnings",
                should_repair=False,
                round_number=self.rounds,
                issue_signature=signature,
                stages=stages,
                actions=tuple(valid_actions),
                termination_reason="no_progress",
                reason="audit issue signature did not change after repair",
            )

        self._previous_signature = signature
        self.rounds += 1
        return DefenseLoopDecision(
            status="repair",
            should_repair=True,
            round_number=self.rounds,
            issue_signature=signature,
            stages=stages,
            actions=tuple(valid_actions),
            reason="executable repair actions are available",
        )
