"""CLI tests for LLM compile review queue commands."""

import json
from pathlib import Path

from wiki_langgraph.cli import main
from wiki_langgraph.manifest import load_manifest


def _candidate(tmp_path: Path, candidate_id: str = "note-md-abc123") -> Path:
    root = tmp_path / "data" / ".wiki-langgraph" / "candidates" / candidate_id
    root.mkdir(parents=True)
    (root / "candidate.md").write_text("# Candidate\n\nReviewed body.\n", encoding="utf-8")
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "id": candidate_id,
                "source_relpath": "note.md",
                "target_relpath": "note.md",
                "raw_sha256": "a" * 64,
                "risk_reasons": ["existing_note_overwrite"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def _review_env(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    monkeypatch.setenv("WIKI_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("WIKI_DATA_RAW_DIR", str(raw))
    monkeypatch.setenv("WIKI_DATA_WIKI_DIR", str(wiki))
    monkeypatch.setenv("WIKI_MANIFEST_PATH", str(tmp_path / "manifest.json"))


def test_review_list_prints_pending_candidates(tmp_path: Path, monkeypatch, capsys) -> None:  # noqa: ANN001
    _review_env(monkeypatch, tmp_path)
    _candidate(tmp_path)

    assert main(["review", "list"]) == 0

    out = capsys.readouterr().out
    assert "note-md-abc123" in out
    assert "note.md -> note.md" in out
    assert "existing_note_overwrite" in out


def test_review_show_prints_metadata_and_candidate(tmp_path: Path, monkeypatch, capsys) -> None:  # noqa: ANN001
    _review_env(monkeypatch, tmp_path)
    _candidate(tmp_path)

    assert main(["review", "show", "note-md-abc123"]) == 0

    out = capsys.readouterr().out
    assert '"source_relpath": "note.md"' in out
    assert "# Candidate" in out


def test_review_approve_writes_candidate_updates_manifest_and_removes_queue(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:  # noqa: ANN001
    _review_env(monkeypatch, tmp_path)
    candidate_dir = _candidate(tmp_path)

    assert main(["review", "approve", "note-md-abc123"]) == 0

    assert (tmp_path / "wiki" / "note.md").read_text(encoding="utf-8") == "# Candidate\n\nReviewed body.\n"
    assert load_manifest(tmp_path / "manifest.json")["hashes"]["note.md"] == "a" * 64
    assert not candidate_dir.exists()
    assert "approved note-md-abc123" in capsys.readouterr().out


def test_review_reject_removes_candidate(tmp_path: Path, monkeypatch, capsys) -> None:  # noqa: ANN001
    _review_env(monkeypatch, tmp_path)
    candidate_dir = _candidate(tmp_path)

    assert main(["review", "reject", "note-md-abc123"]) == 0

    assert not candidate_dir.exists()
    assert "rejected note-md-abc123" in capsys.readouterr().out
