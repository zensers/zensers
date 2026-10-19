import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_output_spec_does_not_enforce_five_segment():
    text = read_text(ROOT / "prompts" / "_shared" / "output_spec.md")
    assert not re.search(r"Every analysis section MUST follow this structure", text, re.I)


def test_output_spec_keeps_data_consistency_hard_constraint():
    text = read_text(ROOT / "prompts" / "_shared" / "output_spec.md")
    assert re.search(r"Data Consistency \(HARD CONSTRAINT\)", text, re.I)


def test_chapter_write_allows_rewrite():
    text = read_text(ROOT / "src" / "agents" / "fixed_agents" / "report_upgrade" / "prompts" / "chapter_write.tmpl")
    assert "禁止从头重写" not in text
    assert "精修≠重写" not in text
