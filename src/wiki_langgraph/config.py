"""Application settings loaded from environment and optional `.env`."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator, model_validator
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
    output_profile: str = Field(
        default="okf",
        description=(
            "Compiled markdown profile: okf (Open Knowledge Format) or obsidian (legacy wikilink vault)."
        ),
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
    graph_ingest_timeout_sec: int = Field(
        default=60,
        ge=1,
        description="LangGraph node timeout for ingest.",
    )
    graph_compile_timeout_sec: int = Field(
        default=3600,
        ge=1,
        description="LangGraph node timeout for compile_wiki. Keep high for optional local LLM authoring.",
    )
    graph_index_timeout_sec: int = Field(
        default=900,
        ge=1,
        description="LangGraph node timeout for index, including optional QMD refresh/embed.",
    )
    graph_lint_timeout_sec: int = Field(
        default=300,
        ge=1,
        description="LangGraph node timeout for vault lint.",
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
    qmd_candidate_limit: int = Field(default=40, ge=1, le=1000)
    qmd_no_rerank: bool = Field(
        default=False,
        description="If true, pass --no-rerank to qmd query for faster CPU-friendly retrieval.",
    )
    qmd_chunk_strategy: str = Field(
        default="regex",
        description="QMD chunking mode for query/embed: `regex` or newer AST-backed `auto`.",
    )
    qmd_query_timeout_sec: int = Field(default=120, ge=5, le=600)
    qmd_refresh: bool = Field(
        default=False,
        description=(
            "After writing wiki files, optionally run `qmd update` and `qmd embed -c <collection>` in the "
            "index step. Default false keeps the minimal run free of QMD requirements."
        ),
    )
    qmd_refresh_timeout_sec: int = Field(default=600, ge=30, le=3600)
    qmd_embed_max_docs_per_batch: int | None = Field(default=None, ge=1)
    qmd_embed_max_batch_mb: int | None = Field(default=None, ge=1)
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
    llm_compile_review: str = Field(
        default="off",
        description=(
            "LLM compile review routing: off (write generated notes), risky (queue only risky "
            "candidates), or all (queue every generated candidate)."
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

    @field_validator("output_profile", mode="before")
    @classmethod
    def _output_profile(cls, value: object) -> str:
        if isinstance(value, str):
            x = value.lower().strip()
            if x in {"obsidian", "okf"}:
                return x
        return "okf"

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

    @field_validator("qmd_no_rerank", mode="before")
    @classmethod
    def _coerce_qmd_no_rerank(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @field_validator("qmd_chunk_strategy", mode="before")
    @classmethod
    def _qmd_chunk_strategy(cls, value: object) -> str:
        if isinstance(value, str):
            x = value.lower().strip()
            if x in ("regex", "auto"):
                return x
        return "regex"

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

    @field_validator("llm_compile_review", mode="before")
    @classmethod
    def _llm_compile_review(cls, value: object) -> str:
        if isinstance(value, str):
            x = value.lower().strip()
            if x in {"off", "risky", "all"}:
                return x
        return "off"

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

    # Langfuse uses the unprefixed names below so the same `.env` works for the
    # Python SDK, its LangChain callback handler, and the local v4 server.
    langfuse_public_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_PUBLIC_KEY", "WIKI_LANGFUSE_PUBLIC_KEY"),
        repr=False,
        description="Langfuse project public key; tracing is disabled when unset.",
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_SECRET_KEY", "WIKI_LANGFUSE_SECRET_KEY"),
        repr=False,
        description="Langfuse project secret key; never commit this value.",
    )
    langfuse_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "WIKI_LANGFUSE_BASE_URL"),
        description="Langfuse API base URL, for example http://localhost:3300.",
    )
    langfuse_tracing_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("LANGFUSE_TRACING_ENABLED", "WIKI_LANGFUSE_TRACING_ENABLED"),
        description="Enable Langfuse tracing when both project keys are configured; opt-in by default.",
    )
    langfuse_tracing_environment: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LANGFUSE_TRACING_ENVIRONMENT", "WIKI_LANGFUSE_TRACING_ENVIRONMENT"
        ),
        description="Optional Langfuse environment label such as development or production.",
    )
    langfuse_tracing_release: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_TRACING_RELEASE", "WIKI_LANGFUSE_TRACING_RELEASE"),
        description="Optional Langfuse release label for comparing application versions.",
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
        """Directory for generated OKF markdown wiki pages."""
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
