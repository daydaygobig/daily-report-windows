import json
import struct
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.db_migrations import _ensure_default_prompt_templates
from app.integrations.image_generation import detect_image_dimensions
from app.models.prompt_template import PromptTemplate
from app.repositories.task_repo import TaskRepository
from app.services import image_card_service
from app.services.execution_service import _image_card_meta
from app.services.task_service import _apply_image_card_job_settings, _image_task_fields


def test_detect_png_dimensions_without_decoding_image():
    content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 2144, 3824)

    assert detect_image_dimensions(content, "image/png") == (2144, 3824)


def test_image_execution_meta_reports_requested_and_actual_dimensions():
    execution = SimpleNamespace(
        raw_response=json.dumps(
            {
                "type": "image_card",
                "block_count": 1,
                "image_model_name": "gpt-image-2",
                "aspect_ratio": "9:16",
                "resolution": "4k",
                "size": "2160x3840",
                "request_params": {"model": "gpt-image-2", "n": 1, "size": "2160x3840", "output_format": "png"},
                "deliveries": [
                    {
                        "image_index": 1,
                        "status": "success",
                        "requested_size": "2160x3840",
                        "actual_size": "2144x3824",
                        "size_bytes": 2_335_109,
                        "mime_type": "image/png",
                        "webhooks": [{"webhook_name": "通知群", "status": "success", "image_key": "img_1"}],
                    }
                ],
            },
            ensure_ascii=False,
        )
    )

    meta = _image_card_meta(execution)

    assert meta["请求尺寸"] == "2160x3840"
    assert meta["生成状态"] == "成功"
    assert meta["推送状态"] == "成功"
    assert meta["图片列表"][0]["实际尺寸"] == "2144x3824"
    assert meta["图片列表"][0]["文件大小"] == "2.23 MB"


def test_image_execution_meta_marks_old_records_without_dimensions():
    execution = SimpleNamespace(
        raw_response=json.dumps(
            {
                "type": "image_card",
                "block_count": 1,
                "size": "2160x3840",
                "deliveries": [{"image_index": 1, "size_bytes": 1024, "mime_type": "image/png", "webhooks": []}],
            }
        )
    )

    meta = _image_card_meta(execution)

    assert meta["图片列表"][0]["实际尺寸"] == "-"


def test_image_job_owns_split_rule_instead_of_template():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    template = PromptTemplate(
        name="图片提示词",
        content="手绘风格",
        template_type="image",
        image_split_enabled=False,
        image_split_prompt=None,
    )
    db.add(template)
    db.commit()

    result = _apply_image_card_job_settings(
        db,
        SimpleNamespace(task_type="image_card"),
        {
            "image_prompt_template_id": template.id,
            "image_split_enabled": True,
            "image_split_prompt": image_card_service.DEFAULT_IMAGE_SPLIT_PROMPT,
        },
    )

    assert result["image_prompt"] == "手绘风格"
    assert result["image_split_enabled"] is True
    assert result["image_split_prompt"] == image_card_service.DEFAULT_IMAGE_SPLIT_PROMPT


def test_report_task_writes_legacy_image_split_defaults():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    compatibility_fields = _image_task_fields(db, {"prompt_template_id": None}, target_type="report")

    task = TaskRepository().create_task(
        db,
        obj_in={
            "name": "日报兼容测试",
            "task_type": "report",
            "prompt": "测试提示词",
            "talkers": [],
            "push_webhook_ids": [],
            **compatibility_fields,
        },
    )
    db.commit()

    assert task.image_split_enabled is False
    assert task.image_split_prompt is None


def test_default_prompt_templates_rename_legacy_without_overwriting_content(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'defaults.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE prompt_templates (
                    id INTEGER PRIMARY KEY,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    name VARCHAR(120) NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    description TEXT,
                    template_type TEXT NOT NULL DEFAULT 'regular',
                    image_split_enabled INTEGER NOT NULL DEFAULT 0,
                    image_split_prompt TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO prompt_templates
                    (created_at, updated_at, name, content, template_type, image_split_enabled)
                VALUES
                    (CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '职场案例聊天总结（测试）', '用户已修改的正文', 'regular', 0)
                """
            )
        )

    _ensure_default_prompt_templates(engine)

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name, content FROM prompt_templates ORDER BY id")).mappings().all()

    assert rows[0] == {"name": "职场案例聊天总结（默认）", "content": "用户已修改的正文"}
    assert rows[1]["name"] == "职场案例手绘长图（默认）"
