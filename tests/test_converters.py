"""converters 特征测试：锁住 ORM → dict 的回退规则（chatlog 三态、模型序列缺省、JSON 容错）。"""

from __future__ import annotations

from app.models.job import Job
from app.models.task import Task
from app.utils.converters import job_to_dict, task_to_dict


def make_job(**kw) -> Job:
    defaults = dict(
        task_id=1,
        name="作业",
        start_time="09:00",
        end_time="23:00",
        schedule_type="daily",
    )
    defaults.update(kw)
    return Job(**defaults)


def test_task_to_dict_model_sequence_fallback():
    task = Task(name="t", task_type="report", prompt="p", model_id=7, image_model_id=9)
    data = task_to_dict(task)
    assert data["model_sequence"] == [{"model_id": 7, "max_attempts": 2}]
    assert data["image_model_sequence"] == [{"model_id": 9, "max_attempts": 2}]


def test_task_to_dict_prefers_stored_sequence():
    task = Task(
        name="t",
        prompt="p",
        model_sequence='[{"model_id": 3, "max_attempts": 5}]',
    )
    assert task_to_dict(task)["model_sequence"] == [{"model_id": 3, "max_attempts": 5}]


def test_task_to_dict_json_defaults_on_invalid():
    task = Task(name="t", prompt="p", talkers="不是JSON")
    data = task_to_dict(task)
    assert data["talkers"] == []
    assert data["push_webhook_ids"] == []
    assert data["card_input_source"] == "chatlog"
    assert data["topic_style_config"] == {}


def test_job_to_dict_chatlog_three_state_fallback():
    # chatlog_backup_enabled 为 NULL 时回落 task.store_chatlog
    task_with_store = Task(name="t1", prompt="p", store_chatlog=True)
    job_null_enabled = make_job(chatlog_backup_enabled=None)
    job_null_enabled.task = task_with_store
    assert job_to_dict(job_null_enabled)["chatlog_backup_enabled"] is True
    assert job_to_dict(job_null_enabled)["chatlog_backup_formats"] == ["txt"]

    task_without_store = Task(name="t2", prompt="p", store_chatlog=False)
    job_null_enabled.task = task_without_store
    assert job_to_dict(job_null_enabled)["chatlog_backup_enabled"] is False
    assert job_to_dict(job_null_enabled)["chatlog_backup_formats"] is None


def test_job_to_dict_explicit_flag_wins():
    task = Task(name="t", prompt="p", store_chatlog=True)
    job = make_job(chatlog_backup_enabled=False)
    job.task = task
    data = job_to_dict(job)
    assert data["chatlog_backup_enabled"] is False
    assert data["chatlog_backup_formats"] is None


def test_job_to_dict_formats_passthrough():
    task = Task(name="t", prompt="p")
    job = make_job(chatlog_backup_enabled=True, chatlog_backup_formats='["md","txt"]')
    job.task = task
    assert job_to_dict(job)["chatlog_backup_formats"] == ["md", "txt"]


def test_job_to_dict_defaults():
    task = Task(name="t", prompt="p")
    job = make_job()
    job.task = task
    data = job_to_dict(job)
    assert data["github_config"] is None
    assert data["topic_text_layout"] == "per_topic"
    assert data["topic_text_merge_threshold"] == 3
    assert data["image_aspect_ratio"] == "auto"
    assert data["max_image_count"] == 6
    job.display_order = 5
    assert job_to_dict(job)["display_order"] == 5
