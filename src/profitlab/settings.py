import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_application_revision() -> str:
    """Identify the executable checkout unless an experiment names a revision.

    A package version is intentionally not sufficient during local development: it
    stays unchanged while pipeline behavior is edited. Include the complete tracked
    Git worktree patch and untracked-file manifest when available, so uncommitted
    checkouts do not silently enter the same evaluation cohort. Installed builds fall
    back to the package version rather than failing at settings construction.
    """
    try:
        root = Path(__file__).resolve().parents[2]
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, check=True,
                              capture_output=True, text=True, timeout=1).stdout.strip()
        patch = subprocess.run(['git', 'diff', '--binary', 'HEAD'], cwd=root, check=True,
                               capture_output=True, timeout=2).stdout
        untracked = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=root,
                                   check=True, capture_output=True, text=True, timeout=1).stdout
        fingerprint = hashlib.sha256(patch + untracked.encode()).hexdigest()[:12]
        return f'git-{head[:12]}-{fingerprint}'
    except (OSError, subprocess.SubprocessError):
        return 'package-0.1.0'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(Path("data"), validation_alias="PROFITLAB_DATA_DIR")
    # This is the packaged executable release; deployments may override it with an
    # immutable build/VCS revision. ``unknown`` remains an explicit non-comparable
    # opt-in for environments where neither identity can be established.
    application_revision: str = Field(default_factory=_default_application_revision,
                                      validation_alias='PROFITLAB_APPLICATION_REVISION')
    host: str = Field("127.0.0.1", validation_alias="PROFITLAB_HOST")
    port: int = Field(8000, ge=1, le=65535, validation_alias="PROFITLAB_PORT")
    stage_timeout: float = Field(2400, gt=0, le=3600)
    run_total_timeout: float = Field(3600, gt=0, le=14400)
    demo_stage_delay: float = Field(2, ge=0, le=30)
    chunk_target_tokens: int = Field(1500, ge=100)
    chunk_overlap_tokens: int = Field(180, ge=0)
    chunk_request_budget: int = Field(24000, ge=1000, le=28000)
    chunk_question_overhead: int = Field(2000, ge=500)
    chunk_max_count: int = Field(10000, ge=1)
    screen_keep_threshold: float = Field(0.65, ge=0, le=1)
    screen_uncertain_threshold: float = Field(0.20, ge=0, le=1)
    screen_max_requests: int = Field(2000, ge=1)
    screen_total_timeout: float = Field(1800, gt=0, le=3600)
    screen_recovery_max_chunks: int = Field(12, ge=0)
    sec_user_agent: str = ""
    sec_requests_per_second: float = Field(2, gt=0, le=10)
    sec_timeout: float = Field(15, gt=0, le=60)
    sec_total_timeout: float = Field(120, gt=0, le=300)
    sec_retries: int = Field(2, ge=0, le=4)
    sec_max_history_files: int = Field(20, ge=1, le=100)
    sec_max_response_bytes: int = Field(20000000, ge=1024)
    random_ticker_attempts: int = Field(5, ge=1, le=12)
    random_batch_max_reports: int = Field(5, ge=1, le=12)
    random_batch_max_attempts: int = Field(12, ge=1, le=48)
    random_batch_continue_after_failure: bool = True
    typesafe_api_key: SecretStr = SecretStr("")
    typesafe_base_url: str = 'https://api.typesafe.ai'
    typesafe_model: str = 'jev-latest'
    max_http_attempts: int = Field(3, ge=1, le=5)
    provider_timeout: float = Field(30, gt=0, le=120)
    provider_total_timeout: float = Field(120, gt=0, le=300)
    provider_max_response_bytes: int = Field(2000000, ge=1024)
    structured_output_repairs: int = Field(1, ge=0, le=2)
    writer_max_requests: int = Field(6, ge=1, le=20)
    writer_max_tool_calls: int = Field(8, ge=1, le=30)
    llm_reasoning_effort: Literal['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'] | None = None
    llm_output_mode: Literal['tool', 'native'] = 'tool'
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-5.6-luna"
    # Outline navigation deliberately uses a cheap, fast model independently of the
    # later findings model.  Large windows keep a 2,000-line filing to a few calls.
    outline_model: str = 'gpt-5.6-luna'
    outline_window_lines: int = Field(900, ge=100, le=3000)
    outline_overlap_lines: int = Field(60, ge=0, le=400)
    outline_prompt_version: str = 'outline-hierarchy-v2'
    # Jev receives only short, sanitized outline descriptors.  These bounds keep
    # section discovery cheap and make its exploration policy inspectable.
    section_score_prompt_version: str = 'section-score-v1'
    section_score_batch_size: int = Field(8, ge=1, le=25)
    section_score_request_char_budget: int = Field(8000, ge=1000, le=30000)
    section_score_keep_threshold: float = Field(.65, ge=0, le=1)
    section_score_uncertain_threshold: float = Field(.20, ge=0, le=1)
    section_score_max_selected: int = Field(12, ge=1, le=100)
    # The bounded uncertain band is explored by detailed chunk scoring.  It is
    # not a Findings input: quote-backed chunk scoring still decides retention.
    # Five covers the first post-threshold reserve without materially widening
    # the normal 12-section candidate set.
    section_score_max_uncertain: int = Field(5, ge=0, le=100)
    # T39 experiment: preserve a tiny source-vocabulary reserve beside Jev's
    # bounded section ranking. It is never a semantic eligibility judgement.
    source_reserve_pattern_version: str = 'target-shaped-source-reserve-v1'
    source_reserve_max_sections: int = Field(3, ge=0, le=25)
    # Independent Jev batches share one connection pool, while this bound keeps a
    # single run from overwhelming the provider or losing useful checkpoints.
    v2_provider_concurrency: int = Field(3, ge=1, le=12)
    chunk_score_prompt_version: str = 'chunk-score-v1'
    chunk_score_batch_size: int = Field(4, ge=1, le=20)
    chunk_score_request_char_budget: int = Field(22000, ge=1000, le=60000)
    chunk_score_max_requests: int = Field(100, ge=1, le=2000)
    chunk_score_total_timeout: float = Field(900, gt=0, le=3600)
    chunk_score_keep_threshold: float = Field(.65, ge=0, le=1)
    chunk_score_uncertain_threshold: float = Field(.20, ge=0, le=1)
    chunk_score_max_retained: int = Field(12, ge=1, le=100)
    # Preserve at most one high-scoring chunk from each bounded-uncertain outline
    # section. It still passes detailed Jev scoring before Findings sees it.
    chunk_score_uncertain_section_reserve: int = Field(5, ge=0, le=25)
    chunk_score_source_reserve: int = Field(3, ge=0, le=25)
    chunk_score_max_uncertain: int = Field(4, ge=0, le=100)
    chunk_score_retained_text_char_budget: int = Field(48000, ge=1000, le=1000000)
    chunk_score_overlap_dedupe_ratio: float = Field(.65, ge=0, le=1)
    # T39 source-context diagnostics are bounded and never replace flat chunk retention.
    source_context_prompt_version: str = 'source-context-v2-batched'
    # These are diagnostic calls made after flat chunk selection.  They must have
    # their own call cap: an insufficient first pass can otherwise multiply one
    # retained source line into every configured expansion ring.
    source_context_max_blocks: int = Field(250, ge=1, le=5000)
    source_context_max_requests: int = Field(36, ge=1, le=500)
    source_context_batch_size: int = Field(8, ge=1, le=50)
    source_context_rings: tuple[int, ...] = (2, 8, 24)
    source_context_request_char_budget: int = Field(12000, ge=1000, le=30000)
    source_context_role_threshold: float = Field(.65, ge=0, le=1)
    source_context_role_margin: float = Field(.10, ge=0, le=1)
    source_context_eligibility_threshold: float = Field(.65, ge=0, le=1)
    # Findings receive only the small retained visible-evidence set.  One repair is
    # intentionally permitted for a malformed citation; uncited prose is rejected.
    findings_prompt_version: str = 'findings-v5-jev-types'
    findings_max_requests: int = Field(2, ge=1, le=10)
    findings_total_timeout: float = Field(300, gt=0, le=1800)
    findings_request_char_budget: int = Field(60000, ge=1000, le=1000000)
    # T41 is a layout experiment over visible, independently citable lines.  These
    # limits deliberately do not decide financial eligibility or use later-stage data.
    findings_packet_version: str = 'findings-core-packets-v1'
    findings_packet_max_cores: int = Field(8, ge=1, le=50)
    findings_packet_context_lines: int = Field(2, ge=0, le=8)
    findings_packet_uncertainty_reserve: int = Field(12, ge=0, le=100)
    finding_type_max_requests: int = Field(12, ge=0, le=100)
    finding_type_request_char_budget: int = Field(30000, ge=1000, le=60000)
    finding_type_prompt_version: str = 'finding-type-v2-outline-context'
    evaluation_scale_prompt_version: str = 'evaluation-scale-v1'
    evaluation_scale_max_pairs: int = Field(12, ge=0, le=100)
    evaluation_scale_request_char_budget: int = Field(12000, ge=1000, le=30000)
    # V3 is an isolated source-grounded graph experiment.  None of these settings
    # participate in V2 run identity or storage.
    v3_model: str | None = None
    v3_prompt_version: str = 'evidence-graph-v4'
    v3_window_lines: int = Field(120, ge=10, le=1000)
    v3_window_overlap_lines: int = Field(20, ge=0, le=300)
    v3_max_actions: int = Field(12, ge=1, le=100)
    v3_max_total_source_characters: int = Field(120000, ge=1000, le=1000000)
    v3_max_wall_seconds: float = Field(300, gt=0, le=1800)

    def redactor(self):
        from profitlab.trace import Redactor

        return Redactor([self.typesafe_api_key.get_secret_value(),
                         self.llm_api_key.get_secret_value()])

    def readiness(self) -> dict[str, bool]:
        return {
            "SEC contact configured": self.sec_contact_ready(),
            "Jev key configured": bool(self.typesafe_api_key.get_secret_value()),
            "LLM configuration present": bool(
                self.llm_base_url and self.llm_api_key.get_secret_value() and self.llm_model
            ),
        }

    def sec_contact_ready(self) -> bool:
        import re

        return bool(re.search(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.sec_user_agent)) and not any(
            marker in self.sec_user_agent.lower() for marker in
            ('example.com', 'your-real-contact', 'your-email'))
