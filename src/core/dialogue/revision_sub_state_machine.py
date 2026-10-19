from __future__ import annotations
from enum import Enum
from datetime import datetime
from typing import Optional, List, Tuple, Callable, Awaitable
from uuid import uuid4
import asyncio
import re

from ..adjustment.revision_types import (
    RevisionSession, RevisionAction, RevisionPlan,
    AnalysisResult, SnapshotId, RevisionAbortedException,
)
from ..intent.revision_intent_analyzer import RevisionIntentAnalyzer


class RevisionSubState(Enum):
    INITIAL = "initial"
    CLARIFYING = "clarifying"
    PLAN_PENDING = "plan_pending"
    PLAN_PARTIAL = "plan_partial"
    SNAPSHOTTING = "snapshotting"
    EXECUTING = "executing"
    PREVIEWING = "previewing"
    COMMITTING = "committing"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"
    DRAFTED = "drafted"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"

    def is_terminal(self) -> bool:
        return self in {
            RevisionSubState.COMPLETED,
            RevisionSubState.ABORTED,
            RevisionSubState.FAILED,
            RevisionSubState.ROLLED_BACK,
        }


_VALID_TRANSITIONS: dict[RevisionSubState, list[RevisionSubState]] = {
    RevisionSubState.INITIAL: [
        RevisionSubState.CLARIFYING,
        RevisionSubState.PLAN_PENDING,
        RevisionSubState.DRAFTED,
        RevisionSubState.ABORTED,
        RevisionSubState.FAILED,
    ],
    RevisionSubState.CLARIFYING: [
        RevisionSubState.CLARIFYING,
        RevisionSubState.PLAN_PENDING,
        RevisionSubState.PLAN_PARTIAL,
        RevisionSubState.ABORTED,
    ],
    RevisionSubState.PLAN_PENDING: [
        RevisionSubState.SNAPSHOTTING,
        RevisionSubState.EXECUTING,
        RevisionSubState.PREVIEWING,
        RevisionSubState.CLARIFYING,
        RevisionSubState.ABORTED,
    ],
    RevisionSubState.PLAN_PARTIAL: [
        RevisionSubState.CLARIFYING,
        RevisionSubState.SNAPSHOTTING,
        RevisionSubState.EXECUTING,
        RevisionSubState.ABORTED,
    ],
    RevisionSubState.SNAPSHOTTING: [
        RevisionSubState.EXECUTING,
        RevisionSubState.PREVIEWING,
        RevisionSubState.FAILED,
        RevisionSubState.ABORTED,
    ],
    RevisionSubState.EXECUTING: [
        RevisionSubState.PREVIEWING,
        RevisionSubState.FAILED,
        RevisionSubState.ROLLING_BACK,
        RevisionSubState.ABORTED,
    ],
    RevisionSubState.PREVIEWING: [
        RevisionSubState.COMMITTING,
        RevisionSubState.EXECUTING,
        RevisionSubState.ROLLING_BACK,
        RevisionSubState.CLARIFYING,
        RevisionSubState.ABORTED,
        RevisionSubState.DRAFTED,
    ],
    RevisionSubState.COMMITTING: [
        RevisionSubState.COMPLETED,
        RevisionSubState.ROLLING_BACK,
        RevisionSubState.FAILED,
    ],
    RevisionSubState.COMPLETED: [],
    RevisionSubState.ABORTED: [],
    RevisionSubState.FAILED: [
        RevisionSubState.ROLLING_BACK,
        RevisionSubState.INITIAL,
        RevisionSubState.ABORTED,
    ],
    RevisionSubState.DRAFTED: [
        RevisionSubState.PREVIEWING,
        RevisionSubState.COMMITTING,
        RevisionSubState.CLARIFYING,
    ],
    RevisionSubState.ROLLING_BACK: [
        RevisionSubState.ROLLED_BACK,
        RevisionSubState.FAILED,
    ],
    RevisionSubState.ROLLED_BACK: [
        RevisionSubState.INITIAL,
        RevisionSubState.ABORTED,
    ],
}


class ClarificationLoop:
    MAX_CLARIFICATION_ROUNDS = 3
    CLARIFICATION_TIMEOUT_SECONDS = 300

    POSITIVE_CONFIRMATION_PATTERNS = re.compile(
        r"^(嗯|对|是|好的|可以|行|好|yes|yep|sure|ok|okay|确认|确定|就这样|可以了|没错|对的很|是的|y|1|接受|同意|继续|正确)\s*$",
        re.IGNORECASE,
    )
    ABORT_PATTERNS = re.compile(
        r"^(算了|取消|不要|不用|不了|stop|abort|放弃|跳过|终止|结束|n|no|否|拒绝|不行)\s*$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        analyzer: RevisionIntentAnalyzer,
        report: object,
        ask_user_callback: Optional[Callable[[str], Awaitable[str]]] = None,
    ):
        self._analyzer = analyzer
        self._report = report
        self._ask_user_callback = ask_user_callback or self._default_ask_user
        self._round = 0

    async def _default_ask_user(self, question: str) -> str:
        return "y"

    async def run(self, initial_analysis: AnalysisResult) -> Optional[AnalysisResult]:
        if not initial_analysis.needs_clarification:
            return initial_analysis

        current = initial_analysis
        while self._round < self.MAX_CLARIFICATION_ROUNDS:
            self._round += 1
            question = self._format_question(current)
            response = await self._ask_user(question)

            if response == "__TIMEOUT__":
                return AnalysisResult(
                    intents=current.intents,
                    needs_clarification=False,
                    clarification_questions=[],
                    is_uncertain=True,
                    suggested_section=current.suggested_section,
                    is_global_feedback=current.is_global_feedback,
                    confidence=current.confidence * 0.7,
                )

            if self._is_abort(response):
                raise RevisionAbortedException("User aborted during clarification")

            if self._is_positive_confirmation(response):
                return AnalysisResult(
                    intents=current.intents,
                    needs_clarification=False,
                    clarification_questions=[],
                    is_uncertain=False,
                    suggested_section=current.suggested_section,
                    is_global_feedback=current.is_global_feedback,
                    confidence=max((i.confidence for i in current.intents), default=0.5),
                )

            user_message = f"{response}"
            current = await self._analyzer.analyze(
                user_message, self._report, previous_analysis=current
            )

            if not current.needs_clarification:
                return current

        return self._degrade_to_best_guess(current)

    def _format_question(self, analysis: AnalysisResult) -> str:
        questions = analysis.clarification_questions
        if not questions:
            return "请问您能提供更多信息吗？"
        if len(questions) == 1:
            base = questions[0]
        else:
            base = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        options = []
        if analysis.intents:
            seen = set()
            for intent in analysis.intents:
                op = intent.action_type.value if hasattr(intent.action_type, 'value') else str(intent.action_type)
                if op not in seen:
                    seen.add(op)
                    options.append(op)
        if options:
            base += "\n\n可选操作:\n" + "\n".join(
                f"  {i+1}. {op}" for i, op in enumerate(options)
            )
        return base

    async def _ask_user(self, question: str) -> str:
        try:
            return await asyncio.wait_for(
                self._ask_user_callback(question),
                timeout=self.CLARIFICATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return "__TIMEOUT__"

    def _is_abort(self, response: str) -> bool:
        return bool(self.ABORT_PATTERNS.match(response.strip()))

    def _is_positive_confirmation(self, response: str) -> bool:
        return bool(self.POSITIVE_CONFIRMATION_PATTERNS.match(response.strip()))

    def _degrade_to_best_guess(self, analysis: AnalysisResult) -> AnalysisResult:
        return AnalysisResult(
            intents=analysis.intents,
            needs_clarification=False,
            clarification_questions=[],
            is_uncertain=True,
            suggested_section=analysis.suggested_section,
            is_global_feedback=analysis.is_global_feedback,
            confidence=analysis.confidence * 0.7,
        )


class RevisionSubStateMachine:
    def __init__(self, session: RevisionSession):
        self._session = session
        self._state: RevisionSubState = RevisionSubState.INITIAL
        self._history: List[Tuple[RevisionSubState, RevisionSubState, str]] = []

    @property
    def state(self) -> RevisionSubState:
        return self._state

    @property
    def session(self) -> RevisionSession:
        return self._session

    def start(self) -> None:
        self._state = RevisionSubState.INITIAL
        self._history.clear()
        self._record_transition()

    def transition(self, target: RevisionSubState) -> None:
        allowed = _VALID_TRANSITIONS.get(self._state, [])
        if target not in allowed:
            raise ValueError(
                f"Invalid transition: {self._state.value} -> {target.value}"
            )
        self._state = target
        self._record_transition()

    def _record_transition(self) -> None:
        self._history.append(
            (
                self._state,
                self._state,
                datetime.now().isoformat(),
            )
        )

    def is_terminal(self) -> bool:
        return self._state.is_terminal()

    @property
    def history(self) -> List[Tuple[RevisionSubState, RevisionSubState, str]]:
        return list(self._history)


class RevisionConversationContainer:
    def __init__(self):
        self.revision_sub_machine: Optional[RevisionSubStateMachine] = None
        self.revision_session: Optional[RevisionSession] = None

    @property
    def revision_sub_state(self) -> Optional[RevisionSubState]:
        if self.revision_sub_machine is None:
            return None
        return self.revision_sub_machine.state

    def enter_revision_mode(self, user_message: str = "") -> RevisionSession:
        session = RevisionSession(user_message=user_message)
        self.revision_session = session
        self.revision_sub_machine = RevisionSubStateMachine(session)
        self.revision_sub_machine.start()
        return session

    def exit_revision_mode(self) -> None:
        self.revision_sub_machine = None
        self.revision_session = None

    def set_sub_state(self, target: RevisionSubState) -> None:
        if self.revision_sub_machine is None:
            raise RuntimeError("Not in revision mode")
        self.revision_sub_machine.transition(target)

    def has_active_revision(self) -> bool:
        return (
            self.revision_sub_machine is not None
            and self.revision_session is not None
            and not self.revision_sub_machine.is_terminal()
        )
