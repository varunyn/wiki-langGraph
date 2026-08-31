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


def test_review_gaps_prints_audit_and_report(tmp_path: Path, monkeypatch, capsys) -> None:  # noqa: ANN001
    _review_env(monkeypatch, tmp_path)
    calls: list[tuple[object, str | None, int]] = []

    class Result:
        scope = "Architecture"
        partial = True
        reviewed_paths = ["Architecture/overview.md"]
        omitted_count = 2
        read_allowlist = ["/raw/Architecture/overview.md", "/wiki/Architecture/overview.md"]

        def render_markdown(self) -> str:
            return "# Knowledge-gap review\n\n- finding"

    def fake_review(settings, *, scope, limit):  # noqa: ANN001
        calls.append((settings, scope, limit))
        return Result()

    monkeypatch.setattr("wiki_langgraph.cli.review_knowledge_gaps", fake_review)

    assert main(["review", "gaps", "Architecture", "--limit", "7"]) == 0

    out = capsys.readouterr().out
    assert calls[0][1:] == ("Architecture", 7)
    assert "scope: Architecture" in out
    assert "coverage: partial" in out
    assert "omitted notes: 2" in out
    assert "/raw/Architecture/overview.md" in out
    assert "# Knowledge-gap review" in out


def test_review_gaps_rejects_limit_outside_contract(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    _review_env(monkeypatch, tmp_path)

    try:
        main(["review", "gaps", "--limit", "101"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse validation failure")
