"""LangGraph-based pipeline: collect sources, compile markdown wiki, index, CLI/Q&A hooks."""

__version__ = "0.1.0"

from wiki_langgraph.cli import main
from wiki_langgraph.obsidian_prompt import (
    load_obsidian_markdown_skill_text,
    wiki_llm_system_instructions,
)

__all__ = [
    "__version__",
    "load_obsidian_markdown_skill_text",
    "main",
    "wiki_llm_system_instructions",
]
