"""CLI tests for run command output behavior."""

from wiki_langgraph.cli import main


def test_run_verbose_failure_prints_step_log_once(monkeypatch, capsys) -> None:  # noqa: ANN001
    """A failed verbose run should not print the same step log to stdout and stderr."""

    def fake_run_once(*, settings: object) -> dict[str, object]:
        return {
            "raw_uris": ["note.md"],
            "index_md_written": True,
            "last_error": "lint failed with 1 issue(s)",
            "step_log": ["compile: ok", "lint: failed — 1 issue(s)"],
        }

    monkeypatch.setattr("wiki_langgraph.cli.run_once", fake_run_once)

    assert main(["run", "-v"]) == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert captured.out == ""
    assert combined.count("compile: ok") == 1
    assert combined.count("lint: failed") == 1
