from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Read from the environment (prefix MATHLINGS_) or backend/.env."""

    model_config = SettingsConfigDict(
        env_prefix="MATHLINGS_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )

    database_path: Path = BACKEND_DIR / "data" / "app.db"
    taxonomy_path: Path = BACKEND_DIR / "vendor" / "os-taxonomy"
    # Browser origins allowed to call the API: the Vite dev server by default.
    # Set as a JSON list, e.g. MATHLINGS_CORS_ORIGINS='["http://localhost:5173"]'.
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def database_url(self) -> str:
        return sqlite_url(self.database_path)


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
