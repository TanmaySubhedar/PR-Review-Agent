"""Tests for config loading, env overrides, and save_settings."""

import os
import tempfile
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from pr_review_agent.models.config import Settings


def test_default_settings_are_valid():
    s = Settings()
    assert s.critic_confidence_threshold == 0.7
    assert s.reader_concurrency == 5
    assert s.blast_radius_max_depth == 3
    assert s.blast_radius_max_files == 20


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PR_AGENT_GITHUB_TOKEN", "ghp_test123")
    monkeypatch.setenv("PR_AGENT_AZURE_OPENAI_MODEL", "gpt-4-turbo")

    # Patch config file location to a non-existent file so it reads only env vars.
    with patch("pr_review_agent.config._CONFIG_FILE", tmp_path / "config.toml"):
        from pr_review_agent import config as cfg_module
        # Reload to pick up env vars
        loaded = cfg_module.load_settings()

    assert loaded.github_token == "ghp_test123"
    assert loaded.azure_openai_model == "gpt-4-turbo"


def test_save_and_reload_settings(tmp_path):
    config_file = tmp_path / "config.toml"
    config_dir = tmp_path

    with (
        patch("pr_review_agent.config._CONFIG_FILE", config_file),
        patch("pr_review_agent.config._CONFIG_DIR", config_dir),
    ):
        from pr_review_agent.config import save_settings, load_settings

        save_settings({"github_token": "ghp_saved", "azure_openai_model": "gpt-4o-mini"})
        assert config_file.exists()

        with open(config_file, "rb") as f:
            data = tomllib.load(f)
        assert data["github_token"] == "ghp_saved"
        assert data["azure_openai_model"] == "gpt-4o-mini"

        reloaded = load_settings()
        assert reloaded.github_token == "ghp_saved"
