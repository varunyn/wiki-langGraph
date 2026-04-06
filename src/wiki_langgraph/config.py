"""Application settings loaded from environment and optional `.env`."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from wiki_langgraph.manifest import default_manifest_path


class Settings(BaseSettings):
    """Paths and LLM endpoints for the wiki pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="WIKI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent,
        description="Repository root (contains data/, pyproject.toml).",
    )

    data_raw_dir: Path | None = Field(
        default=None,
        description="Override for raw ingest storage; default data/raw under project_root.",
    )
    data_wiki_dir: Path | None = Field(
        default=None,
        description="Override for compiled wiki markdown; default data/wiki under project_root.",
    )

    openai_api_base: str | None = Field(
        default=None,
        description="OpenAI-compatible base URL (e.g. http://127.0.0.1:8080/v1 for llama-server).",
    )
    openai_api_key: str = Field(
        default="not-needed",
        description="API key for OpenAI-compatible servers that ignore it.",
    )
    llm_model: str = Field(
        default="local",
        description="Model id passed to the chat API when wired in.",
    )
    llm_request_timeout_sec: float = Field(
        default=300.0,
        ge=5.0,
        le=3600.0,
        description=(
            "HTTP timeout in seconds for OpenAI-compatible chat calls (llm_compile, semantic LLM, "
            "deep agent). Local CPU/GPU generation of long notes often exceeds 120s; raise if needed."
        ),
    )
    obsidian_markdown_skill_path: Path | None = Field(
        default=None,
        description=(
            "Optional path to a SKILL.md (or .md) for Obsidian OFM instructions; "
            "else project skills/obsidian-markdown/SKILL.md, else bundled package copy."
        ),
    )
    semantic_links: bool = Field(
        default=False,
        description=(
            "If true, compile adds semantic related-note links (see semantic_backend: "
            "LLM chat or QMD search)."
        ),
    )
    semantic_backend: str = Field(
        default="llm",
        description="When semantic_links: `llm` (needs WIKI_OPENAI_API_BASE) or `qmd` (local QMD CLI).",
    )
    qmd_bin: str = Field(default="qmd", description="QMD executable (must be on PATH or absolute).")
    qmd_collection: str = Field(
        default="cursor",
        description="QMD collection that indexes the vault containing wiki_dir.",
    )
    qmd_min_score: float = Field(default=0.35, ge=0.0, le=1.0)
    qmd_top_n: int = Field(default=10, ge=1, le=100)
    qmd_query_timeout_sec: int = Field(default=120, ge=5, le=600)
    qmd_refresh: bool = Field(
        default=False,
        description=(
            "After writing wiki files, optionally run `qmd update` and `qmd embed -c <collection>` in the "
            "index step. Default false keeps the minimal run free of QMD requirements."
        ),
    )
    qmd_refresh_timeout_sec: int = Field(default=600, ge=30, le=3600)
    qmd_cpu_only: bool = Field(
        default=False,
        description=(
            "If true, QMD subprocesses set NODE_LLAMA_CPP_GPU=false so node-llama-cpp uses CPU "
            "only (avoids Metal shader compile errors on some macOS setups; slower)."
        ),
    )
    llm_compile: bool = Field(
        default=False,
        description=(
            "If true, compile runs each changed raw .md through the chat model (Obsidian OFM) "
            "before writing wiki output; requires WIKI_OPENAI_API_BASE."
        ),
    )
    llm_compile_incremental: bool = Field(
        default=True,
        description=(
            "When llm_compile: if true, only re-author .md files whose raw content changed "
            "(per manifest hashes); if false, re-author every markdown file each run."
        ),
    )
    manifest_path: Path | None = Field(
        default=None,
        description="Override for incremental hash manifest; default data/.wiki-langgraph/manifest.json.",
    )
    llm_compile_max_workers: int = Field(
        default=1,
        ge=1,
        le=64,
        description=(
            "Parallel LLM author calls during llm_compile (thread pool). Default 1: local OpenAI-compatible "
            "servers usually run one completion at a time; higher values can queue and cause mass timeouts. "
            "Raise only if your server truly supports concurrent chat completions."
        ),
    )
    llm_compile_enrich: bool = Field(
        default=False,
        description=(
            "When true and an existing compiled wiki note is found, use an enrichment prompt "
            "that merges new raw source content into the existing article rather than rewriting "
            "from scratch (Pal-style 'enrich, don't replace'). Falls back to full rewrite if no "
            "existing wiki note exists."
        ),
    )
    lint_on_run: bool = Field(
        default=True,
        description=(
            "After index, run the same vault lint as `wiki-langgraph lint`. If any issues are "
            "reported, the run fails (exit code 1). Set false to skip (e.g. CI without full vault)."
        ),
    )

    @field_validator("semantic_links", mode="before")
    @classmethod
    def _coerce_semantic_links(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @field_validator("semantic_backend", mode="before")
    @classmethod
    def _semantic_backend(cls, value: object) -> str:
        if isinstance(value, str):
            x = value.lower().strip()
            if x in ("llm", "qmd"):
                return x
        if value is None:
            return "llm"
        return "llm"

    @field_validator("qmd_refresh", mode="before")
    @classmethod
    def _coerce_qmd_refresh(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @field_validator("qmd_cpu_only", mode="before")
    @classmethod
    def _coerce_qmd_cpu_only(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @field_validator("llm_compile", mode="before")
    @classmethod
    def _coerce_llm_compile(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @field_validator("llm_compile_enrich", mode="before")
    @classmethod
    def _coerce_llm_compile_enrich(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @field_validator("lint_on_run", mode="before")
    @classmethod
    def _coerce_lint_on_run(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @field_validator("llm_compile_incremental", mode="before")
    @classmethod
    def _coerce_llm_compile_incremental(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @field_validator("manifest_path", mode="before")
    @classmethod
    def _empty_manifest_path_none(cls, value: object) -> Path | None:
        if value is None or value == "":
            return None
        if isinstance(value, Path):
            return value
        if isinstance(value, str):
            return Path(value)
        raise TypeError("manifest_path must be a path-like string")

    log_file: Path | None = Field(
        default=None,
        description="Append logs to this path (UTF-8). Unset disables file logging.",
    )
    log_level: str = Field(
        default="INFO",
        description="Log level for file logging: DEBUG, INFO, WARNING, ERROR.",
    )

    @field_validator("log_file", mode="before")
    @classmethod
    def _empty_log_file_none(cls, value: object) -> Path | None:
        if value is None or value == "":
            return None
        if isinstance(value, Path):
            return value
        if isinstance(value, str):
            return Path(value)
        raise TypeError("log_file must be a path-like string")

    def raw_dir(self) -> Path:
        """Directory for fetched raw source blobs."""
        return self.data_raw_dir or (self.project_root / "data" / "raw")

    def wiki_dir(self) -> Path:
        """Directory for generated Obsidian-style markdown wiki pages."""
        return self.data_wiki_dir or (self.project_root / "data" / "wiki")

    def resolved_manifest_path(self) -> Path:
        """Path to the incremental compile hash manifest."""
        return self.manifest_path or default_manifest_path(self.project_root)

    @model_validator(mode="after")
    def _llm_compile_needs_api_base(self) -> Settings:
        if self.llm_compile and not self.openai_api_base:
            msg = "WIKI_OPENAI_API_BASE is required when WIKI_LLM_COMPILE is enabled"
            raise ValueError(msg)
        return self


def load_settings() -> Settings:
    """Load settings (singleton-style for CLI and graph nodes)."""
    return Settings()
