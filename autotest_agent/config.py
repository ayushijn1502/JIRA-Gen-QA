"""
Configuration loader -- reads config.yaml and turns it into validated
Python objects using Pydantic Settings.

How it works:
1. We define nested Pydantic models for each section (jira, gemini, etc.).
2. `AppSettings` loads the YAML file, validates every value, and exposes
   them as typed attributes.
3. Secrets can be overridden by environment variables prefixed with
   AUTOTEST_ (e.g. AUTOTEST_GEMINI__API_KEY overrides gemini.api_key).

Usage:
    settings = load_settings("config.yaml")
    print(settings.jira.url)
"""

from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource, YamlConfigSettingsSource


class JiraSettings(BaseModel):
    """Connection details for JIRA."""

    url: str = Field(default="", description="JIRA instance URL")
    email: str = Field(default="", description="JIRA account email")
    api_token: str = Field(default="", description="JIRA API token")


class GeminiSettings(BaseModel):
    """Configuration for Google Gemini (sole LLM provider for this app)."""

    api_key: str = Field(
        default="",
        description="Google Gemini API key (from Google AI Studio).",
    )
    model_name: str = Field(
        default="gemini-2.5-flash-lite",
        description=(
            "Gemini API model id. Default Flash-Lite is cost-efficient (typical free-tier choice)."
        ),
    )
    max_output_tokens: int | None = Field(
        default=8192,
        description="Cap model output tokens per call; None = library default.",
    )
    max_total_tokens_per_run: int | None = Field(
        default=80_000,
        description=(
            "Soft stop: refuse new LLM calls once cumulative reported tokens exceed this "
            "in one CLI run (None = no cap). Google does not publish remaining quota via API."
        ),
    )
    run_preflight: bool = Field(
        default=True,
        description="If true, verify API key + model with a metadata GET before RAG/JIRA work.",
    )


class GitHubSettings(BaseModel):
    """Configuration for GitHub integration."""

    enabled: bool = Field(
        default=False,
        description="If false, skip branch/PR; generated tests stay on disk only.",
    )
    token: str = Field(default="", description="GitHub personal access token")
    repo: str = Field(default="", description="GitHub repo in owner/name format")
    base_branch: str = Field(default="main", description="Branch to open PRs against")


class RAGSettings(BaseModel):
    """Configuration for the RAG (embedding + vector store) pipeline."""

    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="HuggingFace model name for sentence embeddings",
    )
    chunk_size: int = Field(default=1500, description="Max characters per code chunk")
    chunk_overlap: int = Field(default=200, description="Overlap between consecutive chunks")
    top_k: int = Field(default=5, description="Number of results to return from similarity search")


class PocSettings(BaseModel):
    """
    Low-usage defaults: smaller RAG context and at most two scenarios (positive + negative).
    """

    enabled: bool = Field(
        default=True,
        description="When true, analyze/generate use fewer chunks and cap test_scenarios.",
    )
    analyze_rag_chunks: int = Field(default=2, ge=1, le=20)
    generate_rag_chunks: int = Field(default=2, ge=1, le=20)
    max_test_scenarios: int = Field(
        default=2,
        ge=1,
        le=50,
        description="Cap on test_scenarios after analyze (default 2 = pos + neg).",
    )


class AppSettings(BaseSettings):
    """
    Top-level settings object.  Everything the app needs lives here.
    Call `load_settings(path)` to get an instance.
    """

    model_config = SettingsConfigDict(
        env_prefix="AUTOTEST_",
        env_nested_delimiter="__",
        extra="ignore",
        yaml_file="config.yaml",
    )

    jira: JiraSettings = Field(default_factory=JiraSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    poc: PocSettings = Field(default_factory=PocSettings)
    target_framework_path: str = Field(default="./target_framework")
    docs_path: str = Field(default="./docs")
    max_retries: int = Field(
        default=2,
        description="Pytest failure retries (each retry runs generate again; keep low for quota).",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            YamlConfigSettingsSource(settings_cls),
        )


def load_settings(config_path: str = "config.yaml") -> AppSettings:
    """
    Read a YAML file and return a fully validated AppSettings instance.
    Missing keys get sensible defaults; extra keys are ignored.
    """
    path = Path(config_path)

    class ConfiguredAppSettings(AppSettings):
        model_config = dict(AppSettings.model_config)
        model_config["yaml_file"] = path if path.exists() else None

    return ConfiguredAppSettings()
