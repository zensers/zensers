"""CLI interaction callback for research workflow."""

from typing import Optional


async def build_interaction_callback(console=None):
    if console is None:
        from src.cli.utils import console as default_console
        console = default_console

    try:
        import questionary
    except ImportError:
        console.print("[red]Interactive mode requires questionary library. Run: pip install questionary[/red]")
        raise SystemExit(1)

    async def interaction_callback(step_data: dict) -> dict:
        step_type = step_data.get("step", "unknown")
        next_step = step_data.get("next_step", "")
        step_type_str = str(step_type)

        console.print(f"\n[bold yellow]>>> Interaction Step: {step_type}[/bold yellow]")

        options = step_data.get("options", [])
        instruction = step_data.get("instruction", step_data.get("message", "Please select:"))

        if options:
            return await _handle_options(questionary, console, step_data, options, instruction, next_step)

        framework_options = step_data.get("framework_options", [])
        if framework_options:
            return await _handle_framework(questionary, console, step_data, framework_options, instruction)

        sections_detail = step_data.get("sections_detail", [])
        if sections_detail:
            return await _handle_sections(questionary, console, step_data, sections_detail, instruction, interaction_callback)

        parameters = step_data.get("parameters", {})
        if parameters:
            return await _handle_parameters(questionary, console, step_data, parameters, instruction)

        summary = step_data.get("summary", {})
        if summary or step_data.get("next_step") == "confirm_research":
            return await _handle_summary(questionary, console, step_data, summary, instruction)

        if step_type_str == "preview":
            return await _handle_preview(questionary, console, step_data, instruction)

        return await _handle_fallback(questionary, console, step_data)

    return interaction_callback


async def _handle_options(questionary, console, step_data, options, instruction, next_step):
    console.print(f"\n[cyan]{instruction}[/cyan]")

    choices = []
    for opt in options:
        if isinstance(opt, dict):
            label = opt.get("label", opt.get("value", str(opt)))
            desc = opt.get("desc", opt.get("description", ""))
            if desc:
                choices.append(f"{label} - {desc}")
            else:
                choices.append(label)
        else:
            choices.append(str(opt))

    selected = await questionary.select(
        "Please select:",
        choices=choices,
        style=questionary.Style([
            ('selected', 'fg:green bold'),
            ('pointer', 'fg:green bold'),
            ('question', 'fg:cyan bold'),
        ])
    ).ask_async()

    if selected is None:
        return {"confirmed": False, "cancelled": True}

    selected_idx = choices.index(selected)
    if selected_idx < len(options) and isinstance(options[selected_idx], dict):
        selected_value = options[selected_idx].get("value", selected)
    else:
        selected_value = selected

    if next_step == "select_output_type":
        return {"output_type": selected_value}
    elif next_step == "select_template":
        return {"template_id": selected_value}
    else:
        return {"selected": selected_value, "answer": selected_value}


async def _handle_framework(questionary, console, step_data, framework_options, instruction):
    console.print(f"\n[cyan]{instruction}[/cyan]")

    choices = []
    for fw in framework_options:
        name = fw.get("name", fw.get("id", "Unknown option"))
        desc = fw.get("description", "")
        pages = fw.get("estimated_pages", "")
        sections = fw.get("section_names", [])

        choice_text = f"{name} - {desc}"
        if pages:
            choice_text += f" ({pages})"
        choices.append(choice_text)

        if sections:
            console.print(f"  [dim]{name} includes: {', '.join(sections[:5])}{'...' if len(sections) > 5 else ''}[/dim]")

    selected = await questionary.select(
        "Please select research framework:",
        choices=choices,
    ).ask_async()

    if selected is None:
        return {"confirmed": False}

    selected_idx = choices.index(selected)
    if selected_idx < len(framework_options):
        framework_id = framework_options[selected_idx].get("id", "standard")
    else:
        framework_id = "standard"

    return {"framework_id": framework_id}


async def _handle_sections(questionary, console, step_data, sections_detail, instruction, interaction_callback):
    console.print(f"\n[cyan]{instruction}[/cyan]")

    console.print(f"\n[bold]Research Section List:[/bold]")
    for i, section in enumerate(sections_detail, 1):
        name = section.get("name", section.get("id", "Unknown section"))
        content = section.get("content", "Content to be confirmed")
        console.print(f"  [green]{i}. {name}[/green]")
        console.print(f"     [dim]Research content: {content}[/dim]")

    action = await questionary.select(
        "\nPlease confirm section content:",
        choices=[
            "Confirm, proceed to next step",
            "Need to adjust sections",
            "Go back to previous step (re-select framework)",
            "Cancel research",
        ],
    ).ask_async()

    if action == "Confirm, proceed to next step":
        return {"confirmed": True}
    elif action == "Need to adjust sections":
        section_names = [s.get("name", s.get("id", "")) for s in sections_detail]
        kept_sections = await questionary.checkbox(
            "Please select sections to keep (space to select, enter to confirm, ESC to cancel):",
            choices=section_names,
        ).ask_async()

        if kept_sections is None:
            return await interaction_callback(step_data)

        kept_sections = [s for s in kept_sections if s in section_names]
        if not kept_sections:
            kept_sections = section_names

        adjustments = []
        for s in sections_detail:
            name = s.get("name", s.get("id", ""))
            adjustments.append({
                "id": s.get("id", name),
                "keep": name in kept_sections
            })
        return {"confirmed": True, "adjustments": adjustments}
    elif action == "Go back to previous step (re-select framework)":
        return {"go_back": True}
    else:
        return {"confirmed": False}


async def _handle_parameters(questionary, console, step_data, parameters, instruction):
    console.print(f"\n[cyan]{instruction}[/cyan]")

    result = {}

    param_list = []
    if isinstance(parameters, dict):
        param_list = parameters.get("parameters", [])
        if not param_list:
            for legacy_key in ("region", "time_range", "depth"):
                legacy_param = parameters.get(legacy_key)
                if isinstance(legacy_param, dict):
                    param_list.append({
                        "id": legacy_key,
                        "type": "select",
                        "label": legacy_param.get("label", legacy_key),
                        "default": legacy_param.get("default", ""),
                        "options": [
                            {"value": o, "label": o}
                            for o in legacy_param.get("options", [])
                        ],
                    })
    elif isinstance(parameters, list):
        param_list = parameters

    for param in param_list:
        param_id = param.get("id", "")
        param_type = param.get("type", "select")
        param_label = param.get("label", param_id)
        param_default = param.get("default")
        param_options = param.get("options", [])
        param_required = param.get("required", False)
        param_placeholder = param.get("placeholder", "")

        if param_type == "text":
            prompt_text = f"{param_label}:"
            if param_placeholder:
                prompt_text += f" ({param_placeholder})"
            value = await questionary.text(
                prompt_text,
                default=str(param_default) if param_default else "",
            ).ask_async()
            if value:
                result[param_id] = value
            elif param_default:
                result[param_id] = param_default

        elif param_type in ("select",):
            option_labels = [opt.get("label", opt.get("value", "")) for opt in param_options]
            if len(option_labels) > 1 or param_required:
                selected = await questionary.select(
                    param_label,
                    choices=option_labels,
                ).ask_async()
                if selected:
                    selected_idx = option_labels.index(selected)
                    result[param_id] = param_options[selected_idx].get("value", selected)
                else:
                    result[param_id] = param_default
            else:
                result[param_id] = param_default

        elif param_type == "multi_select":
            option_labels = [opt.get("label", opt.get("value", "")) for opt in param_options]
            selected = await questionary.checkbox(
                f"{param_label} (space to select, enter to confirm):",
                choices=option_labels,
            ).ask_async()
            if selected:
                selected_values = []
                for sel in selected:
                    idx = option_labels.index(sel)
                    selected_values.append(param_options[idx].get("value", sel))
                result[param_id] = selected_values
            else:
                result[param_id] = param_default if param_default else []

        elif param_type == "date":
            value = await questionary.text(
                f"{param_label} (YYYY-MM-DD):",
                default=str(param_default) if param_default else "",
            ).ask_async()
            result[param_id] = value or param_default

        else:
            value = await questionary.text(
                f"{param_label}:",
                default=str(param_default) if param_default else "",
            ).ask_async()
            result[param_id] = value or param_default

    return result


async def _handle_summary(questionary, console, step_data, summary, instruction):
    console.print(f"\n[cyan]{instruction}[/cyan]")

    if summary:
        console.print(f"  [bold]Research Topic:[/bold] {summary.get('topic', 'N/A')}")
        console.print(f"  [bold]Report Type:[/bold] {summary.get('output_type', 'N/A')}")
        console.print(f"  [bold]Region:[/bold] {summary.get('region', 'N/A')}")
        console.print(f"  [bold]Time Range:[/bold] {summary.get('time_range', 'N/A')}")
        console.print(f"  [bold]Sections:[/bold] {', '.join(summary.get('sections', []))}")

    action = await questionary.select(
        "Confirm to start research?",
        choices=["Confirm and start", "Cancel"],
    ).ask_async()

    return {"confirmed": action == "Confirm and start"}


async def _handle_preview(questionary, console, step_data, instruction):
    preview_url = step_data.get("preview_url", "")
    actions = step_data.get("actions", ["confirm", "revise", "cancel"])

    console.print(f"\n[cyan]{instruction}[/cyan]")
    if preview_url:
        console.print(f"  [dim]Preview file: {preview_url}[/dim]")

    action_choices = []
    action_map = {}
    if "confirm" in actions:
        action_choices.append("Confirm and finalize")
        action_map["Confirm and finalize"] = "confirm"
    if "revise" in actions:
        action_choices.append("Needs revision")
        action_map["Needs revision"] = "revise"
    if "cancel" in actions:
        action_choices.append("Cancel")
        action_map["Cancel"] = "cancel"

    if not action_choices:
        action_choices = ["Confirm and finalize", "Needs revision", "Cancel"]
        action_map = {"Confirm and finalize": "confirm", "Needs revision": "revise", "Cancel": "cancel"}

    selected = await questionary.select(
        "Please select action:",
        choices=action_choices,
    ).ask_async()

    action_value = action_map.get(selected, "confirm")

    if action_value == "revise":
        revision_input = await questionary.text(
            "Please enter revision suggestion (e.g., add market size data):",
        ).ask_async()
        return {
            "action": "revise",
            "adjustment": revision_input or "Please improve content quality",
        }

    return {"action": action_value}


async def _handle_fallback(questionary, console, step_data):
    console.print(f"[dim]Step data: {step_data}[/dim]")

    action = await questionary.select(
        "Please select action:",
        choices=["Continue", "Cancel"],
    ).ask_async()

    return {"confirmed": action == "Continue"}
