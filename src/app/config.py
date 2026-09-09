"""Application configuration management using Pydantic settings."""

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration."""

    # FastAPI
    app_name: str = "群聊日报智能助手"
    app_port: int = 8000
    debug: bool = False

    # Database
    db_path: str = "data/app.db"

    # External services
    chatlog_base_url: str = "http://127.0.0.1:5030"
    chatlog_timeout_sec: int = 60
    chatlog_decrypt_before_fetch: bool = True
    chatlog_decrypt_timeout_sec: int = 300
    chatlog_decrypt_cache_enabled: bool = True
    chatlog_decrypt_cache_buffer_sec: int = 0
    chatlog_work_dir: str = ""  # chatlog 命令行工具目录；在 .env（TS_CHATLOG_WORK_DIR）或设置页配置
    weflow_base_url: str = "http://127.0.0.1:5031"
    weflow_access_token: Optional[str] = None
    weflow_page_limit: int = 1000
    weflow_page_timeout_sec: int = 180
    weflow_empty_page_retry: int = 2

    # Scheduler / timezone
    timezone: str = "Asia/Shanghai"
    scheduler_max_workers: int = 4

    # Storage
    local_backup_dir: str = "backups"

    # LLM settings
    default_model_id: Optional[int] = None
    llm_timeout_sec: int = 120
    llm_stream_chunk_size: int = 2048

    # QR code overlay for image cards (bottom-right corner)
    qr_code_enabled: bool = True
    qr_code_url: str = "https://md.xinjianhub.cn/"
    qr_code_caption: str = "喜欢您来"
    qr_code_size_ratio: float = 0.12
    card_renderer_dir: str = ""  # 本地案例卡渲染器目录；空 = 仓库根目录/card_renderer

    # Image card local backup (半卡图/拼接图/内容块原文落盘，便于排查拼接错位)
    image_card_backup_enabled: bool = True
    image_card_backup_dir: str = "backups/image_cards"
    image_card_backup_keep_last: int = 30  # 只保留最近 N 次执行；<=0 表示全部保留

    # Alerting
    default_alert_webhook_id: Optional[int] = None
    alert_suppression_minutes: int = 10

    # Security / encryption
    secrets_key: str = "change-me"

    # CORS
    allowed_origins: List[str] = ["*"]

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), env_file_encoding="utf-8", env_prefix="TS_")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
