"""Chat interaction commands."""
import logging
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    chat_app = typer.Typer(help="Chat interaction")
    parent.add_typer(chat_app, name="chat")

    @chat_app.command("start")
    def chat_start(
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Knowledge bank database path"),
    ):
        """Start interactive chat."""
        import asyncio
        asyncio.run(_chat_start_async(user_id, db_path))

    @chat_app.command("status")
    def chat_status(
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Knowledge bank database path"),
    ):
        """Show chat status."""
        _chat_status_sync(user_id, db_path)


def _chat_status_sync(user_id: str, db_path: Optional[str]):
    """Show chat status (synchronous)."""
    from src.core.memory.knowledge_bank import UserKnowledgeBank
    from src.core.dialogue.state_machine import ConversationStateMachine

    bank = UserKnowledgeBank(user_id, db_path=db_path)
    state_machine = ConversationStateMachine()

    table = Table(title="Chat Status")
    table.add_column("Item", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Current State", state_machine.current_state.value if state_machine.current_state else "N/A")

    console.print(table)
    bank.close()


async def _chat_start_async(user_id: str, db_path: Optional[str]):
    """Start chat asynchronously.

    NOTE: This is a minimal scaffold. Full chat implementation requires
    a proper ChatManager class wrapping ConversationStateMachine + LLMSkill.
    """
    from src.core.memory.knowledge_bank import UserKnowledgeBank
    from src.core.dialogue.state_machine import ConversationStateMachine

    bank = UserKnowledgeBank(user_id, db_path=db_path)
    state_machine = ConversationStateMachine()

    console.print(Panel.fit(
        "[bold blue]Zensers Chat[/bold blue]\n"
        "[dim]Type 'quit' or 'exit' to leave[/dim]\n"
        "[dim]WARNING: Chat is a scaffold - full implementation pending[/dim]"
    ))

    while True:
        try:
            message = console.input("[bold green]You:[/bold green] ")

            if message.strip().lower() in ["quit", "exit"]:
                console.print("[dim]Goodbye![/dim]")
                break

            if message.strip().lower() == "status":
                console.print(f"[dim]Current state: {state_machine.current_state.value if state_machine.current_state else 'N/A'}[/dim]")
                continue

            console.print(f"[bold blue]Assistant:[/bold blue] Received: {message[:100]}")
            console.print(f"[dim](Chat is a scaffold - state: {state_machine.current_state.value if state_machine.current_state else 'N/A'})[/dim]")

        except KeyboardInterrupt:
            console.print("\n[dim]Chat interrupted[/dim]")
            break

    bank.close()
