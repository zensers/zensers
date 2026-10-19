"""Hard validation for the routing -> execution -> report contract.

This module deliberately validates identities before building any dictionary
index.  A report may be delivered with quality warnings, but it must not be
delivered when its planned structure, execution coverage, or artifact version
is inconsistent.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set


class ManifestContractError(ValueError):
    """A hard contract violation that must block delivery."""

    def __init__(self, code: str, details: Optional[Mapping[str, Any]] = None):
        self.code = code
        self.details = dict(details or {})
        message = code if not self.details else f"{code}: {self.details}"
        super().__init__(message)


@dataclass
class ManifestContractResult:
    framework_leaf_ids: Set[str] = field(default_factory=set)
    planned_body_ids: Set[str] = field(default_factory=set)
    manifest_synthesis_ids: Set[str] = field(default_factory=set)
    created_agent_section_ids: Set[str] = field(default_factory=set)
    execution_result_ids: Set[str] = field(default_factory=set)
    actual_body_ids: Set[str] = field(default_factory=set)
    report_slot_ids: Set[str] = field(default_factory=set)
    missing_ids: Set[str] = field(default_factory=set)
    unknown_ids: Set[str] = field(default_factory=set)
    duplicate_ids: Set[str] = field(default_factory=set)
    missing_producers: Set[str] = field(default_factory=set)
    status: str = "passed"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _items(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    return [item for item in (value or []) if isinstance(item, dict)] if isinstance(value, list) else []


def _id(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("section_id") or item.get("id") or item.get("node_id"))
    return _text(getattr(item, "section_id", "") or getattr(item, "agent_id", ""))


def _duplicates(values: Iterable[str]) -> Set[str]:
    seen: Set[str] = set()
    duplicates: Set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _walk_framework(nodes: Any, path: str = "") -> Set[str]:
    leaves: Set[str] = set()
    node_items = _items(nodes)
    sibling_ids = [_text(node.get("node_id") or node.get("section_id") or node.get("id") or node.get("sub_section_id")) for node in node_items]
    sibling_duplicates = _duplicates(sibling_ids)
    if sibling_duplicates:
        raise ManifestContractError("duplicate_section_id", {"ids": sorted(sibling_duplicates)})
    for node in node_items:
        node_id = _text(node.get("node_id") or node.get("section_id") or node.get("id") or node.get("sub_section_id"))
        title = _text(node.get("title") or node.get("name"))
        if not node_id or not title:
            raise ManifestContractError("manifest_invalid", {"node": node})
        full_id = f"{path}::{node_id}" if path else node_id
        children = node.get("sub_sections")
        if children is None:
            children = node.get("subsections")
        if children is None:
            children = node.get("children")
        children = children or []
        if not isinstance(children, list):
            raise ManifestContractError("manifest_invalid", {"section_id": full_id})
        role = _text(node.get("role") or node.get("section_role")).lower()
        slot = _text(node.get("output_slot")).lower()
        is_synthesis = role in {"synthesis", "summary", "conclusion"} or slot in {"exec_summary", "conclusion"}
        if children:
            leaves.update(_walk_framework(children, full_id))
        elif not is_synthesis:
            leaves.add(full_id)
    return leaves


def _producer_ids(item: Mapping[str, Any]) -> Set[str]:
    raw = item.get("producer_agent_ids", {})
    values = raw.values() if isinstance(raw, dict) else [raw]
    result: Set[str] = set()
    for value in values:
        flattened = value if isinstance(value, (list, tuple, set)) else [value]
        result.update(_text(producer) for producer in flattened if _text(producer))
    return result


def _agent_id(agent: Any) -> str:
    return _text(agent.get("agent_id") if isinstance(agent, dict) else getattr(agent, "agent_id", ""))


def validate_manifest_contract(
    framework_tree: Any,
    manifest: Any,
    created_agents: Any,
    execution_results: Any,
    report: Any,
    artifacts: Any,
) -> ManifestContractResult:
    """Validate all identity and version joins, raising on any hard failure."""
    manifest_items = _items(manifest)
    manifest_ids = [_id(item) for item in manifest_items]
    duplicate_ids = _duplicates(manifest_ids)
    if not manifest_items or any(not value for value in manifest_ids):
        raise ManifestContractError("manifest_invalid")
    if duplicate_ids:
        raise ManifestContractError("duplicate_section_id", {"ids": sorted(duplicate_ids)})

    framework_leaf_ids = _walk_framework(framework_tree)
    planned_body_ids = {
        _id(item) for item in manifest_items if _text(item.get("output_slot")).lower() == "body"
    }
    synthesis_items = [
        item for item in manifest_items
        if _text(item.get("output_slot")).lower() in {"exec_summary", "conclusion"}
    ]
    manifest_synthesis_ids = {_id(item) for item in synthesis_items}
    if framework_leaf_ids != planned_body_ids:
        raise ManifestContractError(
            "manifest_invalid",
            {
                "missing": sorted(framework_leaf_ids - planned_body_ids),
                "unknown": sorted(planned_body_ids - framework_leaf_ids),
            },
        )

    required_producers = set().union(*(_producer_ids(item) for item in manifest_items))
    created_ids = {_agent_id(agent) for agent in (created_agents or []) if _agent_id(agent)}
    missing_producers = required_producers - created_ids
    if any(not _producer_ids(item) for item in manifest_items):
        missing_producers.add("<manifest_item_without_producer>")
    if missing_producers:
        raise ManifestContractError("agent_contract_failed", {"missing_producers": sorted(missing_producers)})

    result_items = _items(execution_results)
    execution_keys = [
        _text(item.get("result_id") or item.get("execution_result_id"))
        or f"{_id(item)}::{_text(item.get('agent_id') or item.get('producer_agent_id'))}"
        for item in result_items
    ]
    result_duplicates = _duplicates(execution_keys)
    if result_duplicates:
        raise ManifestContractError("duplicate_section_id", {"ids": sorted(result_duplicates)})
    execution_result_ids = {_id(item) for item in result_items if _id(item)}
    planned_all_ids = set(manifest_ids)
    if execution_result_ids != planned_all_ids:
        raise ManifestContractError(
            "execution_coverage_failed",
            {
                "missing": sorted(planned_all_ids - execution_result_ids),
                "unknown": sorted(execution_result_ids - planned_all_ids),
            },
        )

    if not isinstance(report, dict):
        raise ManifestContractError("report_coverage_failed")
    report_sections = _items(report.get("sections"))
    report_ids = [_id(item) for item in report_sections]
    if any(not value for value in report_ids):
        raise ManifestContractError("unknown_section_id", {"ids": ["<missing>"]})
    report_duplicates = _duplicates(report_ids)
    if report_duplicates:
        raise ManifestContractError("duplicate_section_id", {"ids": sorted(report_duplicates)})
    # Section identity is not enough: the report agent must preserve the
    # manifest's user-facing title exactly.  Otherwise a correct section ID
    # can still render the wrong chapter (the original quality defect).
    manifest_titles = {
        _id(item): _text(item.get("section_name") or item.get("title") or item.get("name"))
        for item in manifest_items
        if _text(item.get("output_slot")).lower() == "body"
    }
    title_mismatches = {}
    for item in report_sections:
        item_id = _id(item)
        expected_title = manifest_titles.get(item_id, "")
        actual_title = _text(item.get("title") or item.get("name"))
        if expected_title and actual_title != expected_title:
            title_mismatches[item_id] = {
                "expected": expected_title,
                "actual": actual_title,
            }
    if title_mismatches:
        raise ManifestContractError("report_title_mismatch", {"sections": title_mismatches})
    actual_body_ids = {value for value in report_ids if value}
    unknown = actual_body_ids - planned_body_ids
    missing = planned_body_ids - actual_body_ids
    if unknown:
        raise ManifestContractError("unknown_section_id", {"ids": sorted(unknown)})
    if missing:
        raise ManifestContractError("report_coverage_failed", {"missing": sorted(missing)})
    report_slot_ids: Set[str] = set()
    for item in synthesis_items:
        slot = _text(item.get("output_slot")).lower()
        if slot in report and _text(report.get(slot)):
            report_slot_ids.add(_id(item))
        else:
            raise ManifestContractError("report_coverage_failed", {"missing_slot": slot, "section_id": _id(item)})

    artifact_items = _items(artifacts)
    if artifact_items:
        versions = {_text(item.get("report_version")) for item in artifact_items}
        manifest_hashes = {_text(item.get("manifest_hash")) for item in artifact_items}
        content_hashes = {_text(item.get("report_content_hash")) for item in artifact_items}
        artifact_hashes = [_text(item.get("artifact_hash")) for item in artifact_items]
        if (
            len(versions) != 1 or not next(iter(versions), "")
            or len(manifest_hashes) != 1 or not next(iter(manifest_hashes), "")
            or len(content_hashes) != 1 or not next(iter(content_hashes), "")
            or any(not value for value in artifact_hashes)
        ):
            raise ManifestContractError("artifact_version_mismatch")
        if len(set(artifact_hashes)) != len(artifact_hashes):
            raise ManifestContractError("artifact_version_mismatch")

    return ManifestContractResult(
        framework_leaf_ids=framework_leaf_ids,
        planned_body_ids=planned_body_ids,
        manifest_synthesis_ids=manifest_synthesis_ids,
        created_agent_section_ids=created_ids,
        execution_result_ids=execution_result_ids,
        actual_body_ids=actual_body_ids,
        report_slot_ids=report_slot_ids,
        duplicate_ids=duplicate_ids | result_duplicates | report_duplicates,
        missing_producers=missing_producers,
    )
