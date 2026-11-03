"""历史案例卡补跑 CLI（不入库：不写执行记录，只生成卡片并发布）。

用法（在项目根目录）：
    poetry run python scripts/backfill_case_cards.py --exec-id 95 --date-dir 2026-08-30 \
        --only-topic 先修车 --task-name 漫道案例卡-0830-补跑

流程与线上 image_card 任务一致：
    历史日报执行的话题全文（同 _load_upstream_report_content 的拼装方式）
    → 任务「漫道职场案例卡-html+生图」的提示词 + 系统指令（同 _build_system_instruction）
    → 任务绑定的文本模型链生成内容块
    → 本地 HTML 引擎渲染长卡 + 小红书 3:4 分页（关系图走任务绑定的图片模型链）
    → 复制到 TS_HTML_CARD_PUBLISH_DIR/<内容日期>/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.config import get_settings  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.model import Model  # noqa: E402
from app.models.prompt_template import PromptTemplate  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.integrations import llm  # noqa: E402
from app.scheduler.parsing import _parse_llm_chunk  # noqa: E402
from app.scheduler.upstream import _extract_report_topic_sections  # noqa: E402
from app.services import html_case_card_service, image_card_service  # noqa: E402

TASK_ID = 6  # 漫道职场案例卡-html+生图
JOB_ID = 9   # 漫道职场案例卡-html+生图（每日作业，取其拆分设置与关系图提示词模板）


def build_report_content(sections: list[dict], *, task_name: str, finished_text: str) -> str:
    blocks = []
    for index, section in enumerate(sections, start=1):
        body = "\n".join(section["lines"]).strip()
        blocks.append(f"### 话题{index}：{section['title']}\n{body}" if body
                      else f"### 话题{index}：{section['title']}")
    return (
        f"以下是任务「{task_name}」（生成于 {finished_text}）最近一次成功输出中 "
        f"{len(sections)} 个话题的完整内容，按输出顺序排列。\n\n" + "\n\n".join(blocks)
    )


def build_system_instruction(task: Task, job: Job, *, time_str: str, talkers: list[str]) -> str:
    result = (
        "请基于聊天记录，根据提示词完成任务。\n"
        f"时间范围: {time_str}\n"
        f"群聊: {', '.join(talkers)}\n"
    )
    image_rules: list[str] = []
    if bool(getattr(job, "image_split_enabled", False)):
        split_prompt = image_card_service.expand_split_prompt(getattr(job, "image_split_prompt", None))
        image_rules.append(f"图片内容拆分规则（必须遵守）：\n{split_prompt}")
    image_rules.append(
        f"图片卡片空内容规则（必须遵守）：\n{image_card_service.NO_IMAGE_CONTENT_INSTRUCTION}"
    )
    return f"{result.rstrip()}\n\n" + "\n\n".join(image_rules)


async def invoke_llm(model: Model, prompt: str) -> str:
    extra_payload = json.loads(model.extra) if model.extra else None
    result_chunks: list[str] = []
    prompt_tokens = None
    completion_tokens = None
    async for chunk in llm.stream_completion(model, prompt=prompt, extra_payload=extra_payload):
        text, prompt_tokens, completion_tokens = _parse_llm_chunk(chunk, prompt_tokens, completion_tokens)
        if text:
            result_chunks.append(text)
    summary = "".join(result_chunks).strip()
    if not summary:
        raise RuntimeError("模型返回为空")
    return summary


def load_model_sequence(db, task: Task) -> list[Model]:
    items: list[dict] = []
    raw = getattr(task, "model_sequence", None)
    if raw:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, list):
            items = [i for i in parsed if isinstance(i, dict)]
    sequence: list[Model] = []
    for item in items:
        model = db.query(Model).filter(Model.id == int(item.get("model_id") or 0)).first()
        if model:
            sequence.append(model)
    if not sequence:
        raise RuntimeError("任务未绑定文本模型")
    return sequence


def load_relation_models(db, task: Task) -> list[Model]:
    items: list[dict] = []
    raw = getattr(task, "image_model_sequence", None)
    if raw:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, list):
            items = [i for i in parsed if isinstance(i, dict)]
    sequence: list[Model] = []
    for item in items:
        model = db.query(Model).filter(Model.id == int(item.get("model_id") or 0)).first()
        if model and (getattr(model, "model_type", "text") or "text") == "image":
            sequence.append(model)
    return sequence


def main() -> None:
    parser = argparse.ArgumentParser(description="历史案例卡补跑（不入库）")
    parser.add_argument("--exec-id", type=int, required=True, help="作为事实来源的日报执行 id")
    parser.add_argument("--date-dir", required=True, help="发布目录的内容日期文件夹名，如 2026-08-30")
    parser.add_argument("--only-topic", default="", help="只保留标题含该关键词的话题（如：先修车）")
    parser.add_argument("--exclude-topic", default="", help="剔除标题含该关键词的话题（如：职场9条）")
    parser.add_argument("--task-name", default="漫道案例卡-补跑", help="本次运行名称（用于卡片工作目录命名）")
    parser.add_argument("--no-publish", action="store_true", help="只生成到工作目录，不复制到发布目录")
    parser.add_argument("--svg", action="store_true", help="关系图用 SVG 确定性渲染（跳过生图模型，杜绝乱码）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将处理的话题，不调用模型")
    args = parser.parse_args()

    settings = get_settings()

    with session_scope() as db:
        task = db.query(Task).filter(Task.id == TASK_ID).first()
        job = db.query(Job).filter(Job.id == JOB_ID).first()
        if not task or not job:
            raise SystemExit(f"任务 {TASK_ID} 或作业 {JOB_ID} 不存在")
        from app.models.execution import Execution
        execution = db.query(Execution).filter(Execution.id == args.exec_id).first()
        if not execution:
            raise SystemExit(f"执行 {args.exec_id} 不存在")

        sections = _extract_report_topic_sections(execution.summary_md or "")
        if not sections:
            raise SystemExit("未能从该执行输出中提取到话题内容")
        if args.only_topic:
            sections = [s for s in sections if args.only_topic in s["title"]]
        if args.exclude_topic:
            sections = [s for s in sections if args.exclude_topic not in s["title"]]
        if not sections:
            raise SystemExit("话题过滤后为空")

        print(f"[源] exec {execution.id}（{execution.started_at}），本次处理 {len(sections)} 个话题：")
        for index, section in enumerate(sections, start=1):
            print(f"  {index}. {section['title']}")

        if args.dry_run:
            return

        # 与 _load_upstream_report_content 相同的拼装方式
        raw_request = json.loads(execution.raw_request or "{}")
        time_str = raw_request.get("chatlog_range") or args.date_dir
        talker_names = raw_request.get("talkers") or ["漫道-只聊工作不聊天"]
        content = build_report_content(
            sections,
            task_name=raw_request.get("task_name") or "漫道日报V2",
            finished_text=str(execution.finished_at or ""),
        )
        system_instruction = build_system_instruction(task, job, time_str=time_str, talkers=talker_names)
        prompt = f"聊天记录:\n{content}\n\n{system_instruction}\n\n{task.prompt}"

        # 关系图：与 delivery 相同，取作业绑定的图片提示词模板（关系图生图提示词）
        relation_prompt_template = ""
        template_id = getattr(job, "image_prompt_template_id", None)
        if template_id:
            template = db.query(PromptTemplate).filter(PromptTemplate.id == int(template_id)).first()
            if template and (template.content or "").strip():
                relation_prompt_template = template.content

        text_models = load_model_sequence(db, task)
        relation_models = [] if args.svg else load_relation_models(db, task)
        print(f"[模型] 文本链：{' → '.join(m.provider for m in text_models)}")
        print(f"[模型] 关系图链：{' → '.join(m.provider for m in relation_models) or '（无，回退SVG）'}")

    # 模型链重试（语义同 _generate_summary_with_model_sequence：逐家尝试，全部失败才终止）
    summary = ""
    last_error: Exception | None = None
    for model in text_models:
        for attempt in (1, 2):
            try:
                print(f"[LLM] 调用 {model.provider}（第 {attempt} 次）…")
                summary = asyncio.run(invoke_llm(model, prompt))
                blocks = image_card_service.parse_content_blocks(
                    summary, split_enabled=True, max_count=12)
                cards = html_case_card_service.parse_case_blocks(blocks)
                if not cards or len(cards) != len(sections):
                    raise ValueError(
                        f"内容块数 {len(cards)} 与话题数 {len(sections)} 不一致")
                if not any(card.facts or card.relations or card.analysis for card in cards):
                    raise ValueError("内容块缺少槽位内容（背景概述/人物关系/分析过程等）")
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(f"[LLM] 失败：{exc}")
                summary = ""
        if summary:
            break
    if not summary:
        raise SystemExit(f"AI 请求全部失败：{last_error}")

    generated_items, final_images, engine_meta = asyncio.run(
        html_case_card_service.render_case_cards(
            blocks=blocks,
            task_name=args.task_name,
            relation_models=relation_models,
            relation_size=str(settings.html_card_relation_image_size or "1536x1024"),
            relation_prompt_template=relation_prompt_template,
        )
    )
    run_dir = Path(engine_meta["output_dir"])
    (run_dir / "blocks_source.txt").write_text(summary, encoding="utf-8")
    for card in engine_meta["cards"]:
        print(f"[卡片] {card['index']}. {card['title']}（{card['size']}，"
              f"关系图 {card['relation_engine']}，分页 {card['page_count']}）")

    if not args.no_publish:
        publish_root = (settings.html_card_publish_dir or "").strip()
        if not publish_root:
            raise SystemExit("TS_HTML_CARD_PUBLISH_DIR 未配置，无法发布")
        result = html_case_card_service.publish_case_cards(
            engine_meta["cards"], publish_root=Path(publish_root), date_dir=args.date_dir)
        print(f"[发布] {result['dir']}（长卡 {len(result['cards'])} 张）")
    print(f"[完成] 工作目录：{run_dir}")


if __name__ == "__main__":
    main()
