"""Interactive REPL for Zensers CLI session area."""
import logging
from typing import Optional, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from src.cli.utils import console as default_console

logger = logging.getLogger(__name__)

REPL_COMMANDS = {
    "/help": "Show available commands",
    "/history": "Show conversation history",
    "/status": "Show current session status",
    "/revise": "Revise a section (/revise <section>)",
    "/confirm": "Confirm preview and generate document",
    "/export": "Export document (/export [docx|pdf|html])",
    "/quit": "Exit the session",
}


class SessionREPL:
    """Interactive session REPL — the core of the session area."""

    def __init__(
        self,
        session_id: str,
        console: Console = default_console,
        api_base_url: Optional[str] = None,
    ):
        self.session_id = session_id
        self.console = console
        self._api_base_url = api_base_url

    async def run(self) -> None:
        """Main REPL loop."""
        self.console.print(Panel.fit(
            f"[bold blue]Zensers Session[/bold blue] — {self.session_id}\n"
            f"[dim]Type your message or /help for commands. /quit to exit.[/dim]"
        ))

        while True:
            try:
                user_input = self.console.input("[bold green]You>[/bold green] ").strip()
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]Session paused. Use 'session attach' to resume.[/dim]")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                should_continue = await self._handle_command(user_input)
                if not should_continue:
                    break
                continue

            await self._handle_message(user_input)

    async def _handle_message(self, message: str) -> None:
        """Send user message to the research interact API."""
        from src.cli.client import ZensersClient, ZensersError

        try:
            async with ZensersClient(base_url=self._api_base_url) as client:
                result = await client.research_interact(
                    session_id=self.session_id,
                    user_message=message,
                )
        except ZensersError as e:
            self.console.print(f"[red]Error: {e.message}[/red]")
            return
        except Exception as e:
            self.console.print(f"[red]Unexpected error: {e}[/red]")
            return

        response = result.get("response", result.get("message", ""))
        if response:
            self.console.print(f"[bold blue]Assistant:[/bold blue]")
            self.console.print(Markdown(str(response)[:2000]))
        else:
            self.console.print("[dim](No response)[/dim]")

        state = result.get("state", result.get("mode", ""))
        if state:
            self.console.print(f"[dim]State: {state}[/dim]")

        step_info = result.get("step_info", {})
        if step_info:
            self._display_step_info(step_info)

    def _display_step_info(self, step_info: Dict[str, Any]) -> None:
        """Display interactive step information."""
        options = step_info.get("options", [])
        if options:
            for i, opt in enumerate(options, 1):
                if isinstance(opt, dict):
                    label = opt.get("label", opt.get("value", ""))
                    desc = opt.get("description", opt.get("desc", ""))
                    self.console.print(f"  [cyan]{i}.[/cyan] {label}" + (f" — {desc}" if desc else ""))

        framework_options = step_info.get("framework_options", [])
        if framework_options:
            for fw in framework_options:
                name = fw.get("name", "")
                desc = fw.get("description", "")
                self.console.print(f"  [cyan]•[/cyan] {name}" + (f" — {desc}" if desc else ""))

    async def _handle_command(self, command_line: str) -> bool:
        """Handle REPL command. Returns False to exit."""
        parts = command_line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            self.console.print("[dim]Exiting session. Use 'session attach' to resume.[/dim]")
            return False

        if cmd == "/help":
            self._cmd_help()
        elif cmd == "/history":
            await self._cmd_history()
        elif cmd == "/status":
            await self._cmd_status()
        elif cmd == "/revise":
            await self._cmd_revise(arg)
        elif cmd == "/confirm":
            await self._cmd_confirm()
        elif cmd == "/export":
            await self._cmd_export(arg)
        else:
            self.console.print(f"[yellow]Unknown command: {cmd}. Type /help for available commands.[/yellow]")

        return True

    def _cmd_help(self) -> None:
        """Show help."""
        table = Table(title="Session Commands")
        table.add_column("Command", style="cyan")
        table.add_column("Description")
        for cmd, desc in REPL_COMMANDS.items():
            table.add_row(cmd, desc)
        self.console.print(table)

    async def _cmd_history(self) -> None:
        """Show conversation history."""
        from src.cli.client import ZensersClient, ZensersError

        try:
            async with ZensersClient(base_url=self._api_base_url) as client:
                result = await client.research_messages(self.session_id, limit=50)
        except ZensersError as e:
            self.console.print(f"[red]Failed to load history: {e.message}[/red]")
            return

        messages = result.get("messages", [])
        if not messages:
            self.console.print("[dim]No conversation history[/dim]")
            return

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            role_style = {"user": "green", "assistant": "blue"}.get(role, "white")
            role_label = {"user": "You", "assistant": "Assistant"}.get(role, role)
            self.console.print(f"[{role_style}]{role_label}[/{role_style}] [dim]{timestamp}[/dim]")
            self.console.print(f"  {str(content)[:200]}")
            self.console.print("")

        if result.get("has_more"):
            self.console.print(f"[dim]... {result['total'] - len(messages)} more messages[/dim]")

    async def _cmd_status(self) -> None:
        """Show session status."""
        from src.cli.client import ZensersClient, ZensersError

        try:
            async with ZensersClient(base_url=self._api_base_url) as client:
                result = await client.research_status(self.session_id)
        except ZensersError as e:
            self.console.print(f"[red]Failed to get status: {e.message}[/red]")
            return

        table = Table(title=f"Session Status: {self.session_id[:12]}")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Status", result.get("status", "unknown"))
        table.add_row("Progress", f"{result.get('progress', 0) * 100:.0f}%")
        if result.get("topic"):
            table.add_row("Topic", result["topic"])
        if result.get("current_phase"):
            table.add_row("Current Phase", result["current_phase"])
        self.console.print(table)

    async def _cmd_revise(self, section: str) -> None:
        """Revise a section."""
        if not section:
            self.console.print("[yellow]Usage: /revise <section_name>[/yellow]")
            return

        from src.cli.client import ZensersClient, ZensersError

        try:
            async with ZensersClient(base_url=self._api_base_url) as client:
                result = await client.research_revise(self.session_id, [section])
        except ZensersError as e:
            self.console.print(f"[red]Revise failed: {e.message}[/red]")
            return

        status = result.get("status", "")
        self.console.print(f"[green]Revision submitted. Status: {status}[/green]")

    async def _cmd_confirm(self) -> None:
        """Confirm preview and generate document."""
        from src.cli.client import ZensersClient, ZensersError

        try:
            async with ZensersClient(base_url=self._api_base_url) as client:
                result = await client.document_generate(
                    self.session_id, output_format="docx"
                )
        except ZensersError as e:
            self.console.print(f"[red]Confirm/generate failed: {e.message}[/red]")
            return

        if result.get("success") or result.get("status") in ("completed", "generating"):
            document_path = result.get("document_path") or result.get("output_path")
            if document_path:
                self.console.print(f"[green][OK] Document generated: {document_path}[/green]")
            else:
                self.console.print(f"[green][OK] Document generation started. {result.get('message', '')}[/green]")
        else:
            self.console.print(f"[red][FAIL] Document generation failed: {result.get('error', result.get('message', 'Unknown error'))}[/red]")

    async def _cmd_export(self, format_arg: str) -> None:
        """Export document."""
        fmt = format_arg.strip() or "docx"
        from src.cli.client import ZensersClient, ZensersError
        from pathlib import Path

        try:
            async with ZensersClient(base_url=self._api_base_url) as client:
                content, content_type = await client.document_export(
                    self.session_id, output_format=fmt
                )
        except FileNotFoundError:
            self.console.print(f"[red]Document not found[/red]")
            return
        except ZensersError as e:
            self.console.print(f"[red]Export failed: {e.message}[/red]")
            return

        ext = {"docx": ".docx", "pdf": ".pdf", "html": ".html"}.get(fmt, ".bin")
        out_path = Path(f"{self.session_id}_export{ext}")
        out_path.write_bytes(content)
        self.console.print(f"[green]Exported: {out_path} ({len(content)} bytes)[/green]")
