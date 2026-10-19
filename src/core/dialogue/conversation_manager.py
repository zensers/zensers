import json
from typing import Optional, Dict, Any
from pathlib import Path
from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState


class ConversationManager:
    def __init__(self, user_id: str = "", knowledge_bank=None):
        self.user_id = user_id
        self.knowledge_bank = knowledge_bank
        self.state_machine = ConversationStateMachine()

    async def process_message(self, message: str) -> Dict[str, Any]:
        self.state_machine.update_context("user_input", message)
        state = self.state_machine.current_state
        return {
            "state": state.value,
            "message": f"已收到您的消息: {message}",
            "context": dict(self.state_machine.context),
        }

    def get_current_state(self) -> ConversationState:
        return self.state_machine.current_state

    def reset(self):
        self.state_machine = ConversationStateMachine()

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self.state_machine.current_state.value,
            "context": dict(self.state_machine.context),
        }

    def get_conversation_summary(self) -> Dict[str, Any]:
        return {
            "state": self.state_machine.current_state.value,
            "context": dict(self.state_machine.context),
            "entities_known": [],
        }

    def save_state(self, path: str):
        data = {
            "user_id": self.user_id,
            "current_state": self.state_machine.current_state.value,
            "context": dict(self.state_machine.context),
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_state(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        state = ConversationState(data["current_state"])
        self.state_machine.current_state = state
        self.state_machine.context.update(data.get("context", {}))
