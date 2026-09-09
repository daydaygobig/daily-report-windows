"""_run_job 主流程特征测试：锁住 export / report / topic_card / image_card 四条分支与失败路径的现有行为。

外部集成（聊天记录、LLM、卡片处理、飞书推送、GitHub、IMA、消息统计上传、磁盘采样）全部
替换为记录式假件，只验证编排逻辑本身：执行记录的状态迁移、字段落库、告警与重试语义。
"""

from __future__ import annotations

import contextlib
import json
from types import SimpleNamespace


from app.models.alert import Alert
from app.models.execution import Execution
from app.models.job import Job
from app.models.task import Task
from app.models.webhook import Webhook
from app.scheduler.service import (
    AiSummaryResult,
    EMPTY_CHATLOG_ERROR_MESSAGE,
    GithubUploadArtifact,
    SchedulerService,
)

REPORT_SUMMARY = "## 日报正文\n今日讨论了职场话题。"
HTML_REPORT = "<!DOCTYPE html><html><head><title>日报</title></head><body><h1>日报</h1></body></html>"


def make_service(monkeypatch, db_session):
    """构造 SchedulerService 并把 _run_job 的外部边界替换为可断言的假件。"""
    import app.scheduler.service as scheduler_module
    from app.services import disk_monitor_service

    @contextlib.contextmanager
    def fake_session_scope():
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    monkeypatch.setattr(scheduler_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(disk_monitor_service, "start_execution_io", lambda db, **kw: SimpleNamespace())
    monkeypatch.setattr(disk_monitor_service, "finish_execution_io", lambda db, **kw: None)

    service = SchedulerService()
    calls = {
        "chatlog": [],
        "llm": [],
        "topic_card": [],
        "image_card": [],
        "push": [],
        "ima": [],
        "stats_github": [],
        "alert_webhook": [],
        "deploy": [],
    }

    async def fake_collect_chatlog(talkers, time_window, telemetry=None):
        calls["chatlog"].append((list(talkers), time_window["time_str"]))
        return "群A 张三 09:00\n今天聊了职场话题\n"

    async def fake_llm(**kwargs):
        calls["llm"].append(kwargs)
        return AiSummaryResult(
            summary=REPORT_SUMMARY,
            prompt_tokens=11,
            completion_tokens=22,
            model=SimpleNamespace(provider="fake-model"),
            prompt_meta={"model_id": 1},
        )

    async def fake_handle_topic_card(**kwargs):
        calls["topic_card"].append(kwargs)
        return "### 话题卡片\n卡片内容"

    async def fake_handle_image_card(**kwargs):
        calls["image_card"].append(kwargs)
        return None

    async def fake_push_feishu(webhooks, task, job, summary, *, raise_on_failure=False):
        calls["push"].append((len(webhooks), summary))
        return True

    async def fake_sync_ima(db, **kwargs):
        calls["ima"].append(kwargs.get("file_paths"))

    async def fake_sync_stats_github(**kwargs):
        calls["stats_github"].append(kwargs.get("stats"))
        return None

    async def fake_notify_alert(db, task, job, message):
        calls["alert_webhook"].append(message)

    async def fake_deploy(**kwargs):
        calls["deploy"].append(kwargs)
        return GithubUploadArtifact(
            repo_path="reports/report.html",
            repo_full_name="owner/repo",
            branch="main",
            github_file_url="https://raw.githubusercontent.com/owner/repo/main/reports/report.html",
            pages_url="https://owner.github.io/repo/reports/report.html",
        )

    monkeypatch.setattr(service, "_collect_chatlog", fake_collect_chatlog)
    monkeypatch.setattr(service, "_generate_summary_with_model_sequence", fake_llm)
    monkeypatch.setattr(service, "_handle_topic_card_result", fake_handle_topic_card)
    monkeypatch.setattr(service, "_handle_image_card_result", fake_handle_image_card)
    monkeypatch.setattr(service, "_push_feishu", fake_push_feishu)
    monkeypatch.setattr(service, "_sync_execution_outputs_to_ima", fake_sync_ima)
    monkeypatch.setattr(service, "_sync_message_stats_to_github", fake_sync_stats_github)
    monkeypatch.setattr(service, "_notify_alert_webhooks", fake_notify_alert)
    monkeypatch.setattr(service, "_deploy_html_to_github", fake_deploy)
    service._calls = calls
    return service


def make_task(db, task_type="report", **kw):
    task = Task(
        name=kw.pop("name", None) or f"任务-{task_type}",
        task_type=task_type,
        prompt="写一份日报",
        talkers=kw.pop("talkers", '["群A"]'),
        **kw,
    )
    db.add(task)
    db.commit()
    return task


def make_job(db, task, **kw):
    job = Job(
        task_id=task.id,
        name=kw.pop("name", None) or f"作业-{task.name}",
        start_time=kw.pop("start_time", "09:00"),
        end_time=kw.pop("end_time", "23:00"),
        schedule_type=kw.pop("schedule_type", "manual"),
        max_retry=kw.pop("max_retry", 0),
        retry_interval_sec=kw.pop("retry_interval_sec", 1),
        **kw,
    )
    db.add(job)
    db.commit()
    return job


async def test_report_branch_success(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)
    task = make_task(db_session, "report", name="日报任务")
    job = make_job(db_session, task, name="日报作业")

    execution_id = await service.run_job_immediately(job.id)

    execution = db_session.get(Execution, execution_id)
    assert execution.status == "success"
    assert execution.summary_md == REPORT_SUMMARY
    assert execution.llm_model_name == "fake-model"
    assert execution.prompt_tokens == 11
    assert execution.completion_tokens == 22
    assert execution.error_msg is None
    assert execution.deploy_status == "none"
    assert execution.is_manual is True
    assert execution.finished_at is not None
    assert execution.duration_ms is not None
    assert service._calls["llm"], "report 分支必须调用 LLM"
    assert service._calls["chatlog"] and service._calls["chatlog"][0][0] == ["群A"]
    assert "~" in service._calls["chatlog"][0][1]
    assert service._calls["push"] == []
    raw = json.loads(execution.raw_request)
    assert raw["task_name"] == "日报任务"
    assert raw["talkers"] == ["群A"]
    assert "chatlog_range" in raw
    db_session.refresh(job)
    assert job.last_run_at is not None


async def test_report_branch_pushes_feishu(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)
    webhook = Webhook(name="群机器人", url_cipher="cipher-text")
    db_session.add(webhook)
    db_session.commit()
    task = make_task(db_session, "report", name="推送日报", push_webhook_ids=str([webhook.id]))
    job = make_job(db_session, task)

    execution_id = await service.run_job_immediately(job.id)

    execution = db_session.get(Execution, execution_id)
    assert execution.status == "success"
    assert len(service._calls["push"]) == 1
    webhook_count, summary = service._calls["push"][0]
    assert webhook_count == 1
    assert summary == REPORT_SUMMARY


async def test_report_branch_github_deploy_success(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)

    async def fake_llm(**kwargs):
        service._calls["llm"].append(kwargs)
        return SimpleNamespace(
            summary=HTML_REPORT,
            prompt_tokens=11,
            completion_tokens=22,
            model=SimpleNamespace(provider="fake-model"),
            prompt_meta={},
        )

    monkeypatch.setattr(service, "_generate_summary_with_model_sequence", fake_llm)
    task = make_task(db_session, "report", name="部署日报")
    job = make_job(db_session, task, github_deploy_enabled=True)

    execution_id = await service.run_job_immediately(job.id)

    execution = db_session.get(Execution, execution_id)
    assert execution.status == "success"
    assert execution.deploy_status == "success"
    assert execution.deploy_url == "https://owner.github.io/repo/reports/report.html"
    assert execution.github_config_id is None
    assert len(service._calls["deploy"]) == 1
    exported = json.loads(execution.exported_files)
    github_items = [item for item in exported if item.get("type") == "github"]
    assert github_items and github_items[0]["deployment_status"] == "success"


async def test_export_branch_skips_llm(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)
    task = make_task(db_session, "export", name="导出任务")
    job = make_job(db_session, task)

    execution_id = await service.run_job_immediately(job.id)

    execution = db_session.get(Execution, execution_id)
    assert execution.status == "success"
    assert execution.summary_md == "数据导出完成，未调用 LLM。"
    assert service._calls["llm"] == []
    assert service._calls["chatlog"], "export 分支仍需拉取聊天记录"
    assert service._calls["push"] == []
    assert json.loads(execution.prompt_usage) == {"chars": {"total": 0}, "tokens": {"total": 0}}
    assert execution.llm_model_name is None
    assert execution.deploy_status == "none"
    raw = json.loads(execution.raw_request)
    assert raw["task_type"] == "export"
    assert raw["llm_skipped"] is True


async def test_topic_card_branch_finalizes(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)
    task = make_task(db_session, "topic_card", name="话题卡任务")
    job = make_job(db_session, task)

    execution_id = await service.run_job_immediately(job.id)

    execution = db_session.get(Execution, execution_id)
    assert execution.status == "success"
    assert execution.summary_md == "### 话题卡片\n卡片内容"
    assert execution.html_backup_path is None
    assert execution.deploy_status == "none"
    assert execution.deploy_url is None
    assert execution.github_config_id is None
    assert len(service._calls["topic_card"]) == 1
    handler_kwargs = service._calls["topic_card"][0]
    assert handler_kwargs["raw_response"] == REPORT_SUMMARY
    assert handler_kwargs["selected_topic"] is None


async def test_image_card_branch_finalizes(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)
    task = make_task(db_session, "image_card", name="图片卡任务")
    job = make_job(db_session, task)

    execution_id = await service.run_job_immediately(job.id)

    execution = db_session.get(Execution, execution_id)
    assert execution.status == "success"
    assert execution.summary_md == REPORT_SUMMARY, "image_card 处理器返回 None 时保留 LLM 原文"
    assert execution.html_backup_path is None
    assert execution.deploy_status == "none"
    assert len(service._calls["image_card"]) == 1


async def test_empty_chatlog_fails_and_alerts(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)

    async def fake_collect_empty(talkers, time_window, telemetry=None):
        return "   "

    monkeypatch.setattr(service, "_collect_chatlog", fake_collect_empty)
    task = make_task(db_session, "report", name="空记录任务")
    job = make_job(db_session, task)

    execution_id = await service.run_job_immediately(job.id)

    execution = db_session.get(Execution, execution_id)
    assert execution.status == "failed"
    assert EMPTY_CHATLOG_ERROR_MESSAGE in execution.error_msg
    assert service._calls["llm"] == []
    assert len(service._calls["alert_webhook"]) == 1
    alert = db_session.query(Alert).one()
    assert alert.category == "execution"
    assert alert.task_id == task.id
    assert alert.job_id == job.id


async def test_missing_talkers_alerts_without_execution(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)
    task = make_task(db_session, "report", name="无群聊任务", talkers="[]")
    job = make_job(db_session, task)

    execution_id = await service.run_job_immediately(job.id)

    assert execution_id is None
    assert service._calls["chatlog"] == []
    assert service._calls["alert_webhook"] == ["任务未配置群聊（请在任务设置中选择至少一个群聊）"]
    assert db_session.query(Alert).count() == 1
    assert db_session.query(Execution).count() == 0


async def test_retry_then_fail_records_error(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)

    async def fake_collect_fail(talkers, time_window, telemetry=None):
        raise RuntimeError("聊天记录拉取断开")

    monkeypatch.setattr(service, "_collect_chatlog", fake_collect_fail)
    task = make_task(db_session, "report", name="重试任务")
    job = make_job(db_session, task, max_retry=1, retry_interval_sec=1)

    execution_id = await service.run_job_immediately(job.id)

    execution = db_session.get(Execution, execution_id)
    assert execution.status == "failed"
    assert "聊天记录拉取断开" in execution.error_msg
    assert service._calls["llm"] == []
    assert len(service._calls["alert_webhook"]) == 1


async def test_disabled_job_returns_none(monkeypatch, db_session):
    service = make_service(monkeypatch, db_session)
    task = make_task(db_session, "report", name="停用任务")
    job = make_job(db_session, task, is_enabled=False)

    execution_id = await service.run_job_immediately(job.id)

    assert execution_id is None
    assert db_session.query(Execution).count() == 0
