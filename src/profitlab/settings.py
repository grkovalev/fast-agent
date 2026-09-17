from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(Path("data"), validation_alias="PROFITLAB_DATA_DIR")
    host: str = Field("127.0.0.1", validation_alias="PROFITLAB_HOST")
    port: int = Field(8000, ge=1, le=65535, validation_alias="PROFITLAB_PORT")
    sec_user_agent: str = ""
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
            "SEC contact configured": bool(self.sec_user_agent)
            and "example.com" not in self.sec_user_agent,
            "Jev key configured": bool(self.typesafe_api_key.get_secret_value()),
            "LLM configuration present": bool(
                self.llm_base_url and self.llm_api_key.get_secret_value() and self.llm_model
            ),
        }
