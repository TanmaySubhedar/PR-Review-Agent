"""Smoke tests: ensure all package modules import without error."""

import importlib
import pytest


MODULES = [
    "pr_review_agent",
    "pr_review_agent.config",
    "pr_review_agent.db",
    "pr_review_agent.cli",
    "pr_review_agent.models.config",
    "pr_review_agent.models.domain",
    "pr_review_agent.models.db",
    "pr_review_agent.tools.treesitter",
    "pr_review_agent.tools.github",
    "pr_review_agent.tools.graphify_mcp",
    "pr_review_agent.tools.repo",
    "pr_review_agent.tools.diff_parser",
    "pr_review_agent.prompts.blast_radius_agent",
    "pr_review_agent.prompts.dispatch",
    "pr_review_agent.prompts.file_reader",
    "pr_review_agent.prompts.reviewer",
    "pr_review_agent.prompts.critic",
    "pr_review_agent.graph.state",
    "pr_review_agent.graph.graph",
    "pr_review_agent.graph.nodes.ingest",
    "pr_review_agent.graph.nodes.symbols",
    "pr_review_agent.graph.nodes.graphify",
    "pr_review_agent.graph.nodes.context",
    "pr_review_agent.graph.nodes.readers",
    "pr_review_agent.graph.nodes.synthesizer",
    "pr_review_agent.graph.nodes.reviewer",
    "pr_review_agent.graph.nodes.critic",
]


@pytest.mark.parametrize("module_path", MODULES)
def test_module_imports(module_path):
    mod = importlib.import_module(module_path)
    assert mod is not None
