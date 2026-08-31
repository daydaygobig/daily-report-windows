from sqlalchemy import create_engine, text

from app.db_migrations import _backfill_image_card_job_templates


def test_backfill_moves_legacy_image_template_to_job(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE prompt_templates (
                    id INTEGER PRIMARY KEY,
                    content TEXT NOT NULL,
                    template_type TEXT NOT NULL,
                    image_split_enabled INTEGER NOT NULL DEFAULT 0,
                    image_split_prompt TEXT
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    prompt_template_id INTEGER
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    image_prompt_template_id INTEGER,
                    image_prompt TEXT,
                    image_split_enabled INTEGER NOT NULL DEFAULT 0,
                    image_split_prompt TEXT
                );
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO prompt_templates
                    (id, content, template_type, image_split_enabled, image_split_prompt)
                VALUES
                    (2, '手绘长图提示词', 'image', 1, '拆图规则');
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO tasks (id, task_type, prompt_template_id)
                VALUES (1, 'image_card', 2);
                """
            )
        )
        conn.execute(text("INSERT INTO jobs (id, task_id) VALUES (1, 1);"))

    _backfill_image_card_job_templates(engine)

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT image_prompt_template_id, image_prompt,
                       image_split_enabled, image_split_prompt
                FROM jobs
                WHERE id = 1
                """
            )
        ).mappings().one()

    assert row["image_prompt_template_id"] == 2
    assert row["image_prompt"] == "手绘长图提示词"
    assert row["image_split_enabled"] == 1
    assert row["image_split_prompt"] == "拆图规则"
