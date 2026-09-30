from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(Path("data"), validation_alias="PROFITLAB_DATA_DIR")
    # This is the packaged executable release; deployments may override it with an
    # immutable build/VCS revision. ``unknown`` remains an explicit non-comparable
    # opt-in for environments where neither identity can be established.
    application_revision: str = Field('0.1.0', validation_alias='PROFITLAB_APPLICATION_REVISION')
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
    provider_timeout: float = Field(60, gt=0, le=120)
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
    section_score_max_uncertain: int = Field(4, ge=0, le=100)
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
    chunk_score_max_uncertain: int = Field(4, ge=0, le=100)
    chunk_score_retained_text_char_budget: int = Field(48000, ge=1000, le=1000000)
    chunk_score_overlap_dedupe_ratio: float = Field(.65, ge=0, le=1)
    # Findings receive only the small retained visible-evidence set.  One repair is
    # intentionally permitted for a malformed citation; uncited prose is rejected.
    findings_prompt_version: str = 'findings-v5-jev-types'
    findings_max_requests: int = Field(2, ge=1, le=10)
    findings_total_timeout: float = Field(300, gt=0, le=1800)
    findings_request_char_budget: int = Field(60000, ge=1000, le=1000000)
    finding_type_max_requests: int = Field(12, ge=0, le=100)
    finding_type_request_char_budget: int = Field(30000, ge=1000, le=60000)
    finding_type_prompt_version: str = 'finding-type-v2-outline-context'
    evaluation_scale_prompt_version: str = 'evaluation-scale-v1'
    evaluation_scale_max_pairs: int = Field(12, ge=0, le=100)
    evaluation_scale_request_char_budget: int = Field(12000, ge=1000, le=30000)

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
