"""converters 特征测试：锁住 ORM → dict 的回退规则（chatlog 三态、模型序列缺省、JSON 容错）。

job_to_dict 现以 JobOut schema 为字段清单；Job 需经过持久化（列默认值生效），
与生产路径（routers/services 传入已入库实体）一致。
"""

from __future__ import annotations


from app.models.github_config import GithubConfig
from app.models.job import Job
from app.models.task import Task
from app.utils.converters import job_to_dict, task_to_dict


def make_task(db, **kw) -> Task:
    task = Task(name=kw.pop("name"), prompt=kw.pop("prompt", "p"), **kw)
    db.add(task)
    db.commit()
    return task


def make_job(db, task, **kw) -> Job:
    job = Job(
        task_id=task.id,
        name=kw.pop("name", "作业"),
        start_time="09:00",
        end_time="23:00",
        schedule_type=kw.pop("schedule_type", "daily"),
        **kw,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


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


def test_job_to_dict_chatlog_three_state_fallback(db_session):
    task_with_store = make_task(db_session, name="t1", store_chatlog=True)
    job_null_enabled = make_job(db_session, task_with_store, chatlog_backup_enabled=None)
    assert job_to_dict(job_null_enabled)["chatlog_backup_enabled"] is True
    assert job_to_dict(job_null_enabled)["chatlog_backup_formats"] == ["txt"]

    task_without_store = make_task(db_session, name="t2", store_chatlog=False)
    job_null_enabled.task = task_without_store
    assert job_to_dict(job_null_enabled)["chatlog_backup_enabled"] is False
    assert job_to_dict(job_null_enabled)["chatlog_backup_formats"] is None


def test_job_to_dict_explicit_flag_wins(db_session):
    task = make_task(db_session, name="t3", store_chatlog=True)
    job = make_job(db_session, task, chatlog_backup_enabled=False)
    data = job_to_dict(job)
    assert data["chatlog_backup_enabled"] is False
    assert data["chatlog_backup_formats"] is None


def test_job_to_dict_formats_passthrough(db_session):
    task = make_task(db_session, name="t4")
    job = make_job(db_session, task, chatlog_backup_enabled=True, chatlog_backup_formats='["md","txt"]')
    assert job_to_dict(job)["chatlog_backup_formats"] == ["md", "txt"]


def test_job_to_dict_defaults_and_extensions(db_session):
    task = make_task(db_session, name="t5")
    job = make_job(db_session, task)
    data = job_to_dict(job)
    assert data["github_config"] is None
    assert data["message_stats_github_config"] is None
    assert data["topic_text_layout"] == "per_topic"
    assert data["topic_text_merge_threshold"] == 3
    assert data["image_aspect_ratio"] == "auto"
    assert data["max_image_count"] == 6
    assert data["display_order"] == 0
    assert data["weekdays"] is None
    assert data["ima_account_name"] is None

    job.display_order = 5
    assert job_to_dict(job)["display_order"] == 5


def test_job_to_dict_nested_config_summary(db_session):
    task = make_task(db_session, name="t6")
    config = GithubConfig(name="我的GH配置", owner="owner", repo="repo", token_cipher="x", branch="main")
    db_session.add(config)
    db_session.commit()
    job = make_job(
        db_session,
        task,
        github_config_id=config.id,
        message_stats_github_enabled=True,
        message_stats_enabled=True,
        message_stats_github_config_id=config.id,
    )
    data = job_to_dict(job)
    assert data["github_config"] == {"id": config.id, "name": "我的GH配置"}
    assert data["message_stats_github_config"] == {"id": config.id, "name": "我的GH配置"}


def test_job_to_dict_weekdays_json_parse(db_session):
    task = make_task(db_session, name="t7")
    job = make_job(db_session, task, weekdays="[1,3]")
    assert job_to_dict(job)["weekdays"] == [1, 3]


def test_job_to_dict_rejects_missing_fields(db_session):
    task = make_task(db_session, name="t8")
    job = make_job(db_session, task)
    data = job_to_dict(job)
    # 与旧版手写清单键集对齐：schema 未覆盖的扩展键必须补齐
    for key in ("github_config", "message_stats_github_config", "chatlog_backup_enabled"):
        assert key in data
