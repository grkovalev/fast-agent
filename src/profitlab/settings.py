from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(Path("data"), validation_alias="PROFITLAB_DATA_DIR")
    host: str = Field("127.0.0.1", validation_alias="PROFITLAB_HOST")
    port: int = Field(8000, ge=1, le=65535, validation_alias="PROFITLAB_PORT")
    chunk_target_tokens: int = Field(1500, ge=100)
    chunk_overlap_tokens: int = Field(180, ge=0)
    chunk_request_budget: int = Field(24000, ge=1000, le=28000)
    chunk_question_overhead: int = Field(2000, ge=500)
    chunk_max_count: int = Field(10000, ge=1)
    sec_user_agent: str = ""
    sec_requests_per_second: float = Field(2, gt=0, le=10)
    sec_timeout: float = Field(15, gt=0, le=60)
    sec_total_timeout: float = Field(120, gt=0, le=300)
    sec_retries: int = Field(2, ge=0, le=4)
    sec_max_history_files: int = Field(20, ge=1, le=100)
    sec_max_response_bytes: int = Field(20000000, ge=1024)
    typesafe_api_key: SecretStr = SecretStr("")
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
