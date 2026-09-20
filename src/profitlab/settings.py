from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(Path("data"), validation_alias="PROFITLAB_DATA_DIR")
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

    def redactor(self):
        from profitlab.trace import Redactor

        return Redactor([self.typesafe_api_key.get_secret_value(),
                         self.llm_api_key.get_secret_value()])

    def readiness(self) -> dict[str, bool]:
        return {
            "Offline demo and interface": True,
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
