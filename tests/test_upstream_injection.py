"""上游日报话题清单注入机制 / 纯日报内容模式的单元测试。"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.execution import Execution
from app.models.task import Task
from app.scheduler.service import (
    UPSTREAM_MAX_AGE_HOURS,
    SchedulerService,
    _extract_report_topic_sections,
    _extract_report_topic_titles,
)
from app.services.task_service import _normalize_card_input_source


HTML_REPORT = """
<html><body>
<h1>漫道</h1>
<h2>一、今日群聊速览</h2>
<h4 class="text-xl"><i class="fas fa-fire"></i> 存钱不靠记账，靠砍支出</h4>
<h4>别光给情绪价值，学提问</h4>
<h4>存钱不靠记账，靠砍支出</h4>
</body></html>
"""

MARKDOWN_REPORT = """# 漫道日报

### 代打卡的忙，你敢帮吗？

正文……

#### 为什么好说话的人总被塞锅？

正文……
"""

HTML_TOPIC_REPORT = """
<html><body>
<h2>一、今日群聊速览</h2>
<p>总消息数量：485</p>
<h2>二、职通时刻・深度话题</h2>
<h4>话题1：工作总背锅？你的SOP该升级了（08:02 - 14:06）</h4>
<p><strong>背景</strong>：群友镜子因客户抱怨收材料太零散，私聊主管建议按时间维度集中收取。</p>
<ul><li>AA昍指出应以「优化流程」为核心，而非「自我感动」</li><li>留痕防甩锅：对接必须获得对方明确反馈</li></ul>
<blockquote><p>「你的进步只来自于得到了老师的认可。」—— AA昍</p></blockquote>
<h4>话题2：从「打卡被开」看懂职场杀鸡儆猴（13:17 - 18:34）</h4>
<p>背景：女子被公司订通宵硬座出差，拒去后被辞退，最终仲裁胜诉。</p>
<h3>三、其他栏目</h3>
<h4>不属于深度话题的话题</h4>
</body></html>
"""

MARKDOWN_TOPIC_REPORT = """# 漫道日报

## 一、职通时刻・深度话题

### 话题1：工作总背锅？你的SOP该升级了

背景：客户抱怨收材料太零散。

金句：「你的进步只来自于得到了老师的认可。」

### 话题2：从「打卡被开」看懂职场杀鸡儆猴

背景：女子被公司订通宵硬座出差，拒去后被辞退。
"""


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _make_task(db, name, task_type, **kwargs):
    task = Task(name=name, task_type=task_type, prompt="p", **kwargs)
    db.add(task)
    db.commit()
    return task


def _make_execution(db, task_id, status, finished_at, summary_md=""):
    execution = Execution(
        task_id=task_id,
        status=status,
        started_at=finished_at or datetime.now(),
        finished_at=finished_at,
        summary_md=summary_md,
    )
    db.add(execution)
    db.commit()
    return execution


def test_extract_titles_from_html_report():
    titles = _extract_report_topic_titles(HTML_REPORT)
    assert titles == ["存钱不靠记账，靠砍支出", "别光给情绪价值，学提问"]


def test_extract_titles_from_markdown_report():
    titles = _extract_report_topic_titles(MARKDOWN_REPORT)
    assert titles == ["代打卡的忙，你敢帮吗？", "为什么好说话的人总被塞锅？"]


def test_extract_titles_empty_for_blank():
    assert _extract_report_topic_titles("") == []
    assert _extract_report_topic_titles("<html><body>没有话题</body></html>") == []


def test_injection_disabled_without_upstream():
    db = _make_db()
    card = _make_task(db, "案例卡", "topic_card")
    service = SchedulerService()
    suffix, meta = service._build_upstream_topic_injection(db, card)
    assert suffix == ""
    assert meta is None


def test_injection_uses_latest_successful_report():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=report.id)
    _make_execution(db, report.id, "failed", datetime.now() - timedelta(hours=1), summary_md="旧的失败记录")
    _make_execution(db, report.id, "success", datetime.now() - timedelta(hours=2), summary_md="<h4>旧话题</h4>")
    latest = _make_execution(
        db,
        report.id,
        "success",
        datetime.now() - timedelta(minutes=10),
        summary_md=HTML_REPORT,
    )

    suffix, meta = SchedulerService()._build_upstream_topic_injection(db, card)

    assert meta["injected"] is True
    assert meta["upstream_execution_id"] == latest.id
    assert meta["topics"] == ["存钱不靠记账，靠砍支出", "别光给情绪价值，学提问"]
    assert "存钱不靠记账，靠砍支出" in suffix
    assert "第零步" in suffix


def test_injection_skips_stale_report():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=report.id)
    _make_execution(
        db,
        report.id,
        "success",
        datetime.now() - timedelta(hours=UPSTREAM_MAX_AGE_HOURS + 1),
        summary_md="<h4>昨天的话题</h4>",
    )

    service = SchedulerService()
    suffix, meta = service._build_upstream_topic_injection(db, card)

    assert suffix == ""
    assert meta["injected"] is False
    assert "小时" in meta["reason"]


def test_injection_skips_when_no_successful_report():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=report.id)
    _make_execution(db, report.id, "failed", datetime.now() - timedelta(minutes=5), summary_md="")

    service = SchedulerService()
    suffix, meta = service._build_upstream_topic_injection(db, card)

    assert suffix == ""
    assert meta["injected"] is False


def test_injection_skips_running_report():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=report.id)
    _make_execution(db, report.id, "running", None, summary_md="")

    service = SchedulerService()
    suffix, meta = service._build_upstream_topic_injection(db, card)

    assert suffix == ""
    assert meta["injected"] is False


def test_injection_skips_report_without_titles():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=report.id)
    _make_execution(db, report.id, "success", datetime.now() - timedelta(minutes=5), summary_md="纯文本没有标题")

    service = SchedulerService()
    suffix, meta = service._build_upstream_topic_injection(db, card)

    assert suffix == ""
    assert meta["injected"] is False


def test_extract_sections_from_html_report():
    sections = _extract_report_topic_sections(HTML_TOPIC_REPORT)
    titles = [s["title"] for s in sections]
    assert titles == [
        "话题1：工作总背锅？你的SOP该升级了（08:02 - 14:06）",
        "话题2：从「打卡被开」看懂职场杀鸡儆猴（13:17 - 18:34）",
    ]
    first = "\n".join(sections[0]["lines"])
    assert "优化流程" in first
    assert "- AA昍指出" in first
    assert "> 「你的进步只来自于得到了老师的认可。」—— AA昍" in first
    assert "总消息数量" not in first
    # 栏目外的话题不收录
    assert all("不属于深度话题" not in t for t in titles)


def test_extract_sections_from_markdown_report():
    sections = _extract_report_topic_sections(MARKDOWN_TOPIC_REPORT)
    titles = [s["title"] for s in sections]
    assert titles == ["话题1：工作总背锅？你的SOP该升级了", "话题2：从「打卡被开」看懂职场杀鸡儆猴"]
    assert "客户抱怨收材料太零散" in "\n".join(sections[0]["lines"])
    assert "漫道日报" not in titles[0]


def test_extract_sections_empty_for_blank():
    assert _extract_report_topic_sections("") == []
    assert _extract_report_topic_sections("<html><body>没有话题</body></html>") == []


def test_report_content_mode_loads_topic_content():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(
        db, "案例卡", "topic_card", upstream_task_id=report.id, card_input_source="report"
    )
    _make_execution(db, report.id, "success", datetime.now() - timedelta(minutes=10), summary_md=HTML_TOPIC_REPORT)

    content, meta = SchedulerService()._load_upstream_report_content(db, card)

    assert meta["mode"] == "report_content"
    assert meta["injected"] is True
    assert meta["topic_count"] == 2
    assert meta["topics"][0].startswith("话题1：")
    assert "话题1：工作总背锅" in content
    assert "优化流程" in content
    assert "深度话题的完整内容" in content


def test_report_content_mode_raises_without_upstream():
    db = _make_db()
    card = _make_task(db, "案例卡", "topic_card", card_input_source="report")
    with pytest.raises(ValueError, match="必须绑定上游日报任务"):
        SchedulerService()._load_upstream_report_content(db, card)


def test_report_content_mode_raises_on_missing_upstream_task():
    db = _make_db()
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=999, card_input_source="report")
    with pytest.raises(ValueError, match="不存在"):
        SchedulerService()._load_upstream_report_content(db, card)


def test_report_content_mode_raises_on_stale_report():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=report.id, card_input_source="report")
    _make_execution(
        db,
        report.id,
        "success",
        datetime.now() - timedelta(hours=UPSTREAM_MAX_AGE_HOURS + 1),
        summary_md=HTML_TOPIC_REPORT,
    )
    with pytest.raises(ValueError, match="小时"):
        SchedulerService()._load_upstream_report_content(db, card)


def test_report_content_mode_raises_without_successful_report():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=report.id, card_input_source="report")
    _make_execution(db, report.id, "failed", datetime.now() - timedelta(minutes=5), summary_md="")
    with pytest.raises(ValueError, match="成功生成的日报"):
        SchedulerService()._load_upstream_report_content(db, card)


def test_report_content_mode_raises_without_sections():
    db = _make_db()
    report = _make_task(db, "漫道日报V2", "report")
    card = _make_task(db, "案例卡", "topic_card", upstream_task_id=report.id, card_input_source="report")
    _make_execution(db, report.id, "success", datetime.now() - timedelta(minutes=5), summary_md="纯文本没有话题")
    with pytest.raises(ValueError, match="话题内容"):
        SchedulerService()._load_upstream_report_content(db, card)


def test_normalize_card_input_source_rules():
    # 卡片任务：默认聊天记录，可选纯日报内容
    assert _normalize_card_input_source(None, task_type="topic_card", upstream_task_id=1) == "chatlog"
    assert _normalize_card_input_source("report", task_type="topic_card", upstream_task_id=1) == "report"
    assert _normalize_card_input_source("report", task_type="image_card", upstream_task_id=1) == "report"
    # 纯日报内容必须绑定上游
    with pytest.raises(ValueError, match="必须绑定上游日报任务"):
        _normalize_card_input_source("report", task_type="topic_card", upstream_task_id=None)
    # 非卡片任务强制聊天记录
    assert _normalize_card_input_source("report", task_type="report", upstream_task_id=1) == "chatlog"
    assert _normalize_card_input_source("report", task_type="export", upstream_task_id=None) == "chatlog"
    # 非法取值
    with pytest.raises(ValueError, match="不支持"):
        _normalize_card_input_source("both", task_type="topic_card", upstream_task_id=1)
