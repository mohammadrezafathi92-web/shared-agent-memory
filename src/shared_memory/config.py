from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMORY_", env_file=".env", extra="ignore")
    database_url: str = "postgresql://memory:memory@localhost:55432/memory"
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1:*", "localhost:*", "testserver"]
    )
    max_body_bytes: int = 1_048_576
    web_dist: str = "web/dist"
