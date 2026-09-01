"""Minimal SQLite schema adjustments for new columns."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from loguru import logger

from .default_prompt_templates import DEFAULT_PROMPT_TEMPLATES


def ensure_schema(engine: Engine) -> None:
    """Add newly introduced columns when running on existing SQLite databases."""

    if engine.dialect.name != "sqlite":
        return
    _ensure_column(engine, "jobs", "github_deploy_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "github_config_id", "INTEGER")
    _ensure_column(engine, "jobs", "html_backup_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "html_backup_path", "TEXT")
    _ensure_column(engine, "jobs", "html_backup_filename_template", "TEXT")
    _ensure_column(engine, "jobs", "html_backup_filename_date_offset_days", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "days_offset", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "display_order", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "executions", "html_backup_path", "TEXT")
    _ensure_column(engine, "executions", "deploy_status", "TEXT NOT NULL DEFAULT 'none'")
    _ensure_column(engine, "executions", "deploy_url", "TEXT")
    _ensure_column(engine, "executions", "deploy_error", "TEXT")
    _ensure_column(engine, "executions", "github_config_id", "INTEGER")
    _ensure_column(engine, "executions", "deploy_record_id", "INTEGER")
    _ensure_column(engine, "github_deployments", "artifact_type", "TEXT")
    _ensure_column(engine, "github_deployments", "artifact_label", "TEXT")
    _ensure_column(engine, "github_deployments", "repo_full_name", "TEXT")
    _ensure_column(engine, "github_deployments", "branch", "TEXT")
    _ensure_column(engine, "github_deployments", "repo_path", "TEXT")
    _ensure_column(engine, "github_deployments", "github_file_url", "TEXT")
    _ensure_column(engine, "github_configs", "view_url_mode", "TEXT NOT NULL DEFAULT 'github_pages'")
    _ensure_column(engine, "github_configs", "view_url_template", "TEXT")
    _ensure_column(engine, "alerts", "execution_id", "INTEGER")
    _ensure_column(engine, "webhooks", "card_mode", "TEXT NOT NULL DEFAULT 'markdown'")
    _ensure_column(engine, "webhooks", "card_header_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "webhooks", "card_header_title", "TEXT")
    _ensure_column(engine, "webhooks", "card_header_subtitle", "TEXT")
    _ensure_column(engine, "webhooks", "card_header_color", "TEXT")
    _ensure_column(engine, "webhooks", "image_render_engine", "TEXT NOT NULL DEFAULT 'satori'")
    _ensure_column(engine, "webhooks", "feishu_app_id", "TEXT")
    _ensure_column(engine, "webhooks", "feishu_app_secret_cipher", "TEXT")
    _ensure_column(engine, "tasks", "system_prompt_custom_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "tasks", "system_prompt_template", "TEXT")
    _ensure_column(engine, "tasks", "system_prompt_include_message_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "tasks", "task_type", "TEXT NOT NULL DEFAULT 'report'")
    _ensure_column(engine, "tasks", "topic_style_config", "TEXT")
    _ensure_column(engine, "tasks", "model_sequence", "TEXT")
    _ensure_column(engine, "models", "model_type", "TEXT NOT NULL DEFAULT 'text'")
    _ensure_column(engine, "prompt_templates", "template_type", "TEXT NOT NULL DEFAULT 'regular'")
    _ensure_column(engine, "prompt_templates", "image_split_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "prompt_templates", "image_split_prompt", "TEXT")
    _ensure_default_prompt_templates(engine)
    _ensure_column(engine, "tasks", "image_model_id", "INTEGER")
    _ensure_column(engine, "tasks", "image_split_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "tasks", "image_split_prompt", "TEXT")
    _ensure_column(engine, "jobs", "message_stats_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "message_stats_formats", "TEXT")
    _ensure_column(engine, "jobs", "message_stats_path", "TEXT")
    _ensure_column(engine, "jobs", "message_stats_filename_template", "TEXT")
    _ensure_column(engine, "jobs", "message_stats_filename_date_offset_days", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "message_stats_github_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "message_stats_github_config_id", "INTEGER")
    _ensure_column(engine, "jobs", "message_stats_github_filename_template", "TEXT")
    _ensure_column(engine, "jobs", "message_stats_github_filename_date_offset_days", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "message_stats_github_root", "TEXT")
    _ensure_column(engine, "jobs", "chatlog_backup_enabled", "INTEGER")
    _ensure_column(engine, "jobs", "chatlog_backup_path", "TEXT")
    _ensure_column(engine, "jobs", "chatlog_backup_formats", "TEXT")
    _ensure_column(engine, "jobs", "chatlog_backup_filename_template", "TEXT")
    _ensure_column(engine, "jobs", "chatlog_backup_filename_date_offset_days", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "github_filename_template", "TEXT")
    _ensure_column(engine, "jobs", "model_output_backup_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "model_output_path", "TEXT")
    _ensure_column(engine, "jobs", "model_output_format", "TEXT")
    _ensure_column(engine, "jobs", "model_output_filename_template", "TEXT")
    _ensure_column(engine, "jobs", "model_output_filename_date_offset_days", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "ima_sync_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "ima_use_default_account", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(engine, "jobs", "ima_account_id", "INTEGER")
    _ensure_column(engine, "jobs", "ima_use_default_target", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(engine, "jobs", "ima_target_type", "TEXT")
    _ensure_column(engine, "jobs", "ima_note_folder_id", "TEXT")
    _ensure_column(engine, "jobs", "ima_note_folder_name", "TEXT")
    _ensure_column(engine, "jobs", "ima_knowledge_base_id", "TEXT")
    _ensure_column(engine, "jobs", "ima_knowledge_base_name", "TEXT")
    _ensure_column(engine, "jobs", "ima_knowledge_folder_id", "TEXT")
    _ensure_column(engine, "jobs", "ima_knowledge_folder_name", "TEXT")
    _ensure_column(engine, "jobs", "weekly_period", "TEXT")
    _ensure_column(engine, "jobs", "weekly_start_day", "INTEGER")
    _ensure_column(engine, "jobs", "weekly_start_time", "TEXT")
    _ensure_column(engine, "jobs", "weekly_end_day", "INTEGER")
    _ensure_column(engine, "jobs", "weekly_end_time", "TEXT")
    _ensure_column(engine, "jobs", "topic_text_layout", "TEXT NOT NULL DEFAULT 'per_topic'")
    _ensure_column(engine, "jobs", "topic_text_merge_threshold", "INTEGER NOT NULL DEFAULT 3")
    _ensure_column(engine, "jobs", "topic_image_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "topic_image_layout", "TEXT NOT NULL DEFAULT 'single'")
    _ensure_column(engine, "jobs", "topic_image_merge_threshold", "INTEGER NOT NULL DEFAULT 3")
    _ensure_column(engine, "jobs", "topic_image_backup_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "topic_image_backup_path", "TEXT")
    _ensure_column(engine, "jobs", "image_prompt_template_id", "INTEGER")
    _ensure_column(engine, "jobs", "image_prompt", "TEXT")
    _ensure_column(engine, "jobs", "image_split_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "image_split_prompt", "TEXT")
    _backfill_image_card_job_templates(engine)
    _ensure_column(engine, "jobs", "image_aspect_ratio", "TEXT NOT NULL DEFAULT 'auto'")
    _ensure_column(engine, "jobs", "image_resolution", "TEXT NOT NULL DEFAULT 'auto'")
    _ensure_column(engine, "jobs", "max_image_count", "INTEGER NOT NULL DEFAULT 6")
    _ensure_column(engine, "jobs", "disk_alert_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "jobs", "disk_alert_threshold_bytes", "INTEGER NOT NULL DEFAULT 104857600")
    _ensure_column(engine, "executions", "exported_files", "TEXT")
    _ensure_column(engine, "executions", "ima_sync_status", "TEXT NOT NULL DEFAULT 'none'")
    _ensure_column(engine, "executions", "ima_sync_error", "TEXT")
    _ensure_column(engine, "executions", "ima_sync_batch_id", "TEXT")
    _ensure_table(
        engine,
        "ima_accounts",
        """
        CREATE TABLE ima_accounts (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            name VARCHAR(255) NOT NULL,
            client_id VARCHAR(255) NOT NULL,
            api_key_cipher TEXT NOT NULL,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            is_default INTEGER NOT NULL DEFAULT 0,
            remark TEXT,
            default_target_type VARCHAR(32) NOT NULL DEFAULT 'knowledge_base',
            default_note_folder_id VARCHAR(255),
            default_note_folder_name VARCHAR(255),
            default_knowledge_base_id VARCHAR(255),
            default_knowledge_base_name VARCHAR(255),
            default_knowledge_folder_id VARCHAR(255),
            default_knowledge_folder_name VARCHAR(255),
            last_test_at DATETIME,
            last_test_status VARCHAR(32),
            last_test_message TEXT
        )
        """,
    )
    _ensure_table(
        engine,
        "ima_sync_settings",
        """
        CREATE TABLE ima_sync_settings (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            default_account_id INTEGER,
            client_id VARCHAR(255),
            api_key_cipher TEXT,
            default_target_type VARCHAR(32) NOT NULL DEFAULT 'knowledge_base',
            default_note_folder_id VARCHAR(255),
            default_note_folder_name VARCHAR(255),
            default_knowledge_base_id VARCHAR(255),
            default_knowledge_base_name VARCHAR(255),
            default_knowledge_folder_id VARCHAR(255),
            default_knowledge_folder_name VARCHAR(255),
            auto_sync_enabled INTEGER NOT NULL DEFAULT 0,
            auto_sync_frequency VARCHAR(16) NOT NULL DEFAULT 'daily',
            auto_sync_weekday INTEGER,
            auto_sync_time VARCHAR(5) NOT NULL DEFAULT '08:00',
            local_sync_path TEXT,
            recursive_enabled INTEGER NOT NULL DEFAULT 1,
            allowed_extensions TEXT,
            last_sync_at DATETIME,
            last_sync_status VARCHAR(32),
            last_sync_summary TEXT
        )
        """,
    )
    _ensure_table(
        engine,
        "ima_sync_records",
        """
        CREATE TABLE ima_sync_records (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            batch_id VARCHAR(64),
            trigger_type VARCHAR(32) NOT NULL,
            source_type VARCHAR(32) NOT NULL,
            source_path TEXT,
            source_name VARCHAR(255),
            source_size INTEGER,
            source_mtime DATETIME,
            ima_account_id INTEGER,
            ima_account_name VARCHAR(255),
            sync_job_id INTEGER,
            task_id INTEGER,
            job_id INTEGER,
            execution_id INTEGER,
            target_type VARCHAR(32) NOT NULL,
            note_folder_id VARCHAR(255),
            note_folder_name VARCHAR(255),
            knowledge_base_id VARCHAR(255),
            knowledge_base_name VARCHAR(255),
            knowledge_folder_id VARCHAR(255),
            knowledge_folder_name VARCHAR(255),
            status VARCHAR(32) NOT NULL,
            skip_reason VARCHAR(64),
            error_code INTEGER,
            error_explanation TEXT,
            error_message TEXT,
            remote_doc_id VARCHAR(255),
            remote_media_id VARCHAR(255)
        )
        """,
    )
    _ensure_table(
        engine,
        "ima_sync_jobs",
        """
        CREATE TABLE ima_sync_jobs (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            name VARCHAR(255) NOT NULL,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            ima_account_id INTEGER,
            target_type VARCHAR(32) NOT NULL DEFAULT 'knowledge_base',
            note_folder_id VARCHAR(255),
            note_folder_name VARCHAR(255),
            knowledge_base_id VARCHAR(255),
            knowledge_base_name VARCHAR(255),
            knowledge_folder_id VARCHAR(255),
            knowledge_folder_name VARCHAR(255),
            local_sync_path TEXT NOT NULL,
            recursive_enabled INTEGER NOT NULL DEFAULT 1,
            allowed_extensions TEXT,
            schedule_frequency VARCHAR(16) NOT NULL DEFAULT 'daily',
            schedule_weekday INTEGER,
            schedule_time VARCHAR(5) NOT NULL DEFAULT '08:00',
            webhook_id INTEGER,
            last_sync_at DATETIME,
            last_sync_status VARCHAR(32),
            last_sync_summary TEXT
        )
        """,
    )
    _ensure_table(
        engine,
        "chat_record_settings",
        """
        CREATE TABLE chat_record_settings (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            provider VARCHAR(16) NOT NULL DEFAULT 'chatlog',
            chatlog_base_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:5030',
            chatlog_timeout_sec INTEGER NOT NULL DEFAULT 60,
            chatlog_decrypt_before_fetch INTEGER NOT NULL DEFAULT 1,
            chatlog_decrypt_timeout_sec INTEGER NOT NULL DEFAULT 300,
            chatlog_decrypt_cache_enabled INTEGER NOT NULL DEFAULT 1,
            chatlog_decrypt_cache_buffer_sec INTEGER NOT NULL DEFAULT 0,
            chatlog_work_dir TEXT NOT NULL DEFAULT 'C:\\Users\\Limmer\\Documents\\chatlog',
            weflow_base_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:5031',
            weflow_token_cipher TEXT,
            weflow_page_limit INTEGER NOT NULL DEFAULT 1000,
            weflow_page_timeout_sec INTEGER NOT NULL DEFAULT 180,
            weflow_empty_page_retry INTEGER NOT NULL DEFAULT 2,
            weflow_include_media INTEGER NOT NULL DEFAULT 0
        )
        """,
    )
    _ensure_table(
        engine,
        "disk_io_records",
        """
        CREATE TABLE disk_io_records (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            execution_id INTEGER,
            task_id INTEGER,
            job_id INTEGER,
            task_name TEXT,
            job_name TEXT,
            task_type VARCHAR(20) NOT NULL DEFAULT 'report',
            is_manual INTEGER NOT NULL DEFAULT 0,
            provider VARCHAR(20) NOT NULL DEFAULT 'unknown',
            started_at DATETIME,
            finished_at DATETIME,
            duration_ms INTEGER,
            backend_read_bytes INTEGER,
            backend_write_bytes INTEGER,
            weflow_read_bytes INTEGER,
            weflow_write_bytes INTEGER,
            weflow_captured INTEGER NOT NULL DEFAULT 0,
            weflow_process TEXT,
            exported_file_bytes INTEGER NOT NULL DEFAULT 0,
            chatlog_decrypt_write_bytes INTEGER NOT NULL DEFAULT 0,
            chatlog_decrypt_status VARCHAR(20),
            chatlog_work_dir TEXT,
            disk_write_bytes INTEGER NOT NULL DEFAULT 0,
            total_read_bytes INTEGER NOT NULL DEFAULT 0,
            total_write_bytes INTEGER NOT NULL DEFAULT 0,
            job_alert_threshold_bytes INTEGER NOT NULL DEFAULT 0,
            job_alert_triggered INTEGER NOT NULL DEFAULT 0,
            job_alert_sent INTEGER NOT NULL DEFAULT 0,
            job_alert_error TEXT,
            media_enabled INTEGER NOT NULL DEFAULT 0,
            is_warning INTEGER NOT NULL DEFAULT 0,
            warning_reason TEXT,
            raw_snapshot TEXT
        )
        """,
    )
    _ensure_table(
        engine,
        "disk_inspection_jobs",
        """
        CREATE TABLE disk_inspection_jobs (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            name VARCHAR(120) NOT NULL,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            schedule_type VARCHAR(30) NOT NULL DEFAULT 'daily',
            schedule_time VARCHAR(5) NOT NULL DEFAULT '09:00',
            schedule_weekday INTEGER,
            schedule_month_day INTEGER,
            cron_expression VARCHAR(120),
            interval_enabled INTEGER NOT NULL DEFAULT 0,
            interval_minutes INTEGER,
            window_start VARCHAR(5) NOT NULL DEFAULT '00:00',
            window_end VARCHAR(5) NOT NULL DEFAULT '24:00',
            window_hours INTEGER NOT NULL DEFAULT 24,
            threshold_bytes INTEGER NOT NULL DEFAULT 1073741824,
            webhook_ids TEXT NOT NULL DEFAULT '[]',
            cooldown_hours INTEGER NOT NULL DEFAULT 6,
            weflow_process_names TEXT,
            last_run_at DATETIME,
            next_run_at DATETIME,
            last_alert_at DATETIME
        )
        """,
    )
    _ensure_table(
        engine,
        "disk_inspection_runs",
        """
        CREATE TABLE disk_inspection_runs (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            inspection_job_id INTEGER,
            inspection_job_name TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'success',
            inspected_at DATETIME NOT NULL,
            window_start DATETIME NOT NULL,
            window_end DATETIME NOT NULL,
            window_hours INTEGER NOT NULL DEFAULT 24,
            threshold_bytes INTEGER NOT NULL DEFAULT 1073741824,
            total_write_bytes INTEGER NOT NULL DEFAULT 0,
            total_read_bytes INTEGER NOT NULL DEFAULT 0,
            max_single_write_bytes INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            record_count INTEGER NOT NULL DEFAULT 0,
            chatlog_decrypt_count INTEGER NOT NULL DEFAULT 0,
            weflow_media_count INTEGER NOT NULL DEFAULT 0,
            alert_sent INTEGER NOT NULL DEFAULT 0,
            alert_error TEXT,
            webhook_ids TEXT,
            summary TEXT
        )
        """,
    )
    _ensure_index(engine, "idx_disk_io_execution_id", "CREATE INDEX idx_disk_io_execution_id ON disk_io_records(execution_id)")
    _ensure_index(engine, "idx_disk_io_finished_at", "CREATE INDEX idx_disk_io_finished_at ON disk_io_records(finished_at)")
    _ensure_index(engine, "idx_disk_inspection_runs_inspected_at", "CREATE INDEX idx_disk_inspection_runs_inspected_at ON disk_inspection_runs(inspected_at)")
    _ensure_column(engine, "chat_record_settings", "chatlog_work_dir", "TEXT NOT NULL DEFAULT 'C:\\Users\\Limmer\\Documents\\chatlog'")
    _ensure_column(engine, "disk_io_records", "chatlog_decrypt_write_bytes", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "disk_io_records", "chatlog_decrypt_status", "VARCHAR(20)")
    _ensure_column(engine, "disk_io_records", "chatlog_work_dir", "TEXT")
    disk_write_added = _ensure_column(engine, "disk_io_records", "disk_write_bytes", "INTEGER NOT NULL DEFAULT 0")
    if disk_write_added:
        with engine.begin() as conn:
            conn.execute(text("UPDATE disk_io_records SET disk_write_bytes = COALESCE(exported_file_bytes, 0)"))
    _ensure_column(engine, "disk_io_records", "job_alert_threshold_bytes", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "disk_io_records", "job_alert_triggered", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "disk_io_records", "job_alert_sent", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "disk_io_records", "job_alert_error", "TEXT")
    _ensure_column(engine, "disk_inspection_jobs", "interval_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(engine, "disk_inspection_jobs", "interval_minutes", "INTEGER")
    _ensure_column(engine, "disk_inspection_jobs", "window_start", "TEXT NOT NULL DEFAULT '00:00'")
    _ensure_column(engine, "disk_inspection_jobs", "window_end", "TEXT NOT NULL DEFAULT '24:00'")
    _ensure_column(engine, "ima_sync_settings", "default_account_id", "INTEGER")
    _ensure_column(engine, "ima_accounts", "remark", "TEXT")
    _ensure_column(engine, "ima_accounts", "default_target_type", "TEXT NOT NULL DEFAULT 'knowledge_base'")
    _ensure_column(engine, "ima_accounts", "default_note_folder_id", "TEXT")
    _ensure_column(engine, "ima_accounts", "default_note_folder_name", "TEXT")
    _ensure_column(engine, "ima_accounts", "default_knowledge_base_id", "TEXT")
    _ensure_column(engine, "ima_accounts", "default_knowledge_base_name", "TEXT")
    _ensure_column(engine, "ima_accounts", "default_knowledge_folder_id", "TEXT")
    _ensure_column(engine, "ima_accounts", "default_knowledge_folder_name", "TEXT")
    _ensure_column(engine, "ima_accounts", "last_test_at", "DATETIME")
    _ensure_column(engine, "ima_accounts", "last_test_status", "TEXT")
    _ensure_column(engine, "ima_accounts", "last_test_message", "TEXT")
    _ensure_column(engine, "ima_sync_records", "ima_account_id", "INTEGER")
    _ensure_column(engine, "ima_sync_records", "ima_account_name", "TEXT")
    _ensure_column(engine, "ima_sync_records", "sync_job_id", "INTEGER")
    _ensure_column(engine, "ima_sync_records", "error_code", "INTEGER")
    _ensure_column(engine, "ima_sync_records", "error_explanation", "TEXT")
    _ensure_column(engine, "ima_sync_jobs", "ima_account_id", "INTEGER")
    _ensure_column(engine, "ima_sync_jobs", "webhook_id", "INTEGER")
    _ensure_index(engine, "idx_jobs_ima_account_id", "CREATE INDEX idx_jobs_ima_account_id ON jobs (ima_account_id)")
    _ensure_index(engine, "idx_ima_accounts_is_default", "CREATE INDEX idx_ima_accounts_is_default ON ima_accounts (is_default)")
    _ensure_index(engine, "idx_ima_sync_jobs_account_id", "CREATE INDEX idx_ima_sync_jobs_account_id ON ima_sync_jobs (ima_account_id)")
    _ensure_index(engine, "idx_ima_sync_records_batch_id", "CREATE INDEX idx_ima_sync_records_batch_id ON ima_sync_records (batch_id)")
    _ensure_index(engine, "idx_ima_sync_records_account_id", "CREATE INDEX idx_ima_sync_records_account_id ON ima_sync_records (ima_account_id)")
    _ensure_index(engine, "idx_ima_sync_records_sync_job_id", "CREATE INDEX idx_ima_sync_records_sync_job_id ON ima_sync_records (sync_job_id)")


def _ensure_column(engine: Engine, table: str, column: str, ddl: str) -> bool:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns(table) or []}
    if column in columns:
        return False
    logger.info("为表 %s 添加缺失字段 %s", table, column)
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    return True


def _backfill_image_card_job_templates(engine: Engine) -> None:
    """Move legacy image-template snapshots from image-card tasks to their jobs."""

    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE jobs
                SET image_prompt_template_id = (
                        SELECT tasks.prompt_template_id
                        FROM tasks
                        JOIN prompt_templates ON prompt_templates.id = tasks.prompt_template_id
                        WHERE tasks.id = jobs.task_id
                          AND tasks.task_type = 'image_card'
                          AND prompt_templates.template_type = 'image'
                    ),
                    image_prompt = (
                        SELECT prompt_templates.content
                        FROM tasks
                        JOIN prompt_templates ON prompt_templates.id = tasks.prompt_template_id
                        WHERE tasks.id = jobs.task_id
                          AND tasks.task_type = 'image_card'
                          AND prompt_templates.template_type = 'image'
                    ),
                    image_split_enabled = COALESCE((
                        SELECT prompt_templates.image_split_enabled
                        FROM tasks
                        JOIN prompt_templates ON prompt_templates.id = tasks.prompt_template_id
                        WHERE tasks.id = jobs.task_id
                          AND tasks.task_type = 'image_card'
                          AND prompt_templates.template_type = 'image'
                    ), 0),
                    image_split_prompt = (
                        SELECT prompt_templates.image_split_prompt
                        FROM tasks
                        JOIN prompt_templates ON prompt_templates.id = tasks.prompt_template_id
                        WHERE tasks.id = jobs.task_id
                          AND tasks.task_type = 'image_card'
                          AND prompt_templates.template_type = 'image'
                    )
                WHERE jobs.image_prompt_template_id IS NULL
                  AND jobs.image_prompt IS NULL
                  AND EXISTS (
                      SELECT 1
                      FROM tasks
                      JOIN prompt_templates ON prompt_templates.id = tasks.prompt_template_id
                      WHERE tasks.id = jobs.task_id
                        AND tasks.task_type = 'image_card'
                        AND prompt_templates.template_type = 'image'
                  )
                """
            )
        )
    if result.rowcount:
        logger.info("已迁移 %s 个图片卡片作业的旧图片提示词配置", result.rowcount)


def _ensure_default_prompt_templates(engine: Engine) -> None:
    """Insert missing built-in templates without renaming or overwriting user data."""

    with engine.begin() as conn:
        for template in DEFAULT_PROMPT_TEMPLATES:
            existing = conn.execute(
                text("SELECT id FROM prompt_templates WHERE name = :name LIMIT 1"),
                {"name": template["name"]},
            ).first()
            if existing:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO prompt_templates
                        (created_at, updated_at, name, content, description, template_type,
                         image_split_enabled, image_split_prompt)
                    VALUES
                        (CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :name, :content, :description,
                         :template_type, 0, NULL)
                    """
                ),
                {
                    "name": template["name"],
                    "content": template["content"],
                    "description": template["description"],
                    "template_type": template["template_type"],
                },
            )


def _ensure_table(engine: Engine, table: str, ddl: str) -> None:
    inspector = inspect(engine)
    if table in inspector.get_table_names():
        return
    logger.info("创建缺失表 %s", table)
    with engine.begin() as conn:
        conn.execute(text(ddl))


def _ensure_index(engine: Engine, name: str, ddl: str) -> None:
    inspector = inspect(engine)
    indexes = {idx["name"] for table in inspector.get_table_names() for idx in inspector.get_indexes(table)}
    if name in indexes:
        return
    logger.info("创建缺失索引 %s", name)
    with engine.begin() as conn:
        conn.execute(text(ddl))
