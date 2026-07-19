"""Utilities for computing and exporting chat message statistics."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

ACTIVE_THRESHOLD = 10
TOP_N_DEFAULT = 10

SENDER_PATTERN = re.compile(r"^(?!>)(.+)\(([^)]+)\)\s+((?:\d{2}-\d{2}\s+)?\d{2}:\d{2}:\d{2})$")
SYSTEM_MESSAGE_LABEL = "\u7cfb\u7edf\u6d88\u606f"
SYSTEM_MESSAGE_PATTERN = re.compile(
    rf"^{SYSTEM_MESSAGE_LABEL}\s+(?:\d{{2}}-\d{{2}}\s+)?\d{{2}}:\d{{2}}:\d{{2}}"
)


@dataclass
class MemberMessageStat:
    nickname: str
    wechat_id: str
    count: int
    percentage: float
    cumulative_percentage: float


@dataclass
class MessageStats:
    total_messages: int
    active_members: int
    top_n_total: int
    top_n_percentage: float
    members: List[MemberMessageStat]
    top_n: int = TOP_N_DEFAULT


def compute_message_stats(
    chatlog_text: str,
    *,
    active_threshold: int = ACTIVE_THRESHOLD,
    top_n: int = TOP_N_DEFAULT,
) -> MessageStats:
    lines = chatlog_text.splitlines()
    member_counts: dict[str, dict[str, int | str]] = {}
    total_messages = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if SYSTEM_MESSAGE_PATTERN.match(line):
            continue

        sender_match = SENDER_PATTERN.match(line)
        if not sender_match:
            continue

        nickname = sender_match.group(1).strip()
        wechat_id = sender_match.group(2).strip()
        total_messages += 1
        export_wechat_id = "wxid_xqev1y1rfnaq29" if wechat_id == "我" else wechat_id

        bucket = member_counts.setdefault(nickname, {"count": 0, "wechat_id": export_wechat_id})
        bucket["count"] = int(bucket["count"]) + 1  # type: ignore[assignment]

    sorted_members = sorted(member_counts.items(), key=lambda item: int(item[1]["count"]), reverse=True)
    members: List[MemberMessageStat] = []
    cumulative = 0
    for nickname, payload in sorted_members:
        count = int(payload["count"])
        percentage = (count / total_messages * 100.0) if total_messages else 0.0
        cumulative += count
        cumulative_percentage = (cumulative / total_messages * 100.0) if total_messages else 0.0
        members.append(
            MemberMessageStat(
                nickname=nickname,
                wechat_id=str(payload["wechat_id"]),
                count=count,
                percentage=round(percentage, 2),
                cumulative_percentage=round(cumulative_percentage, 2),
            )
        )

    active_members = sum(1 for member in members if member.count >= active_threshold)
    top_members = members[:top_n]
    top_n_total = sum(member.count for member in top_members)
    top_n_percentage = (top_n_total / total_messages * 100.0) if total_messages else 0.0

    return MessageStats(
        total_messages=total_messages,
        active_members=active_members,
        top_n_total=top_n_total,
        top_n_percentage=round(top_n_percentage, 2),
        members=members,
        top_n=top_n,
    )


def render_markdown_report(
    stats: MessageStats,
    *,
    report_title: str,
    time_range_label: str,
) -> str:
    lines: List[str] = [
        f"# 群聊天记录统计报告 - {report_title}",
        "",
        f"## 统计时间: {time_range_label}",
        "",
        f"## 消息总数: {stats.total_messages} 条",
        "",
        f"## 日活用户数: {stats.active_members} 人",
        "<!-- 日活定义：每日发言10条以上的用户才算活跃用户 -->",
        "",
        f"## 前十名发言人员总占比: {stats.top_n_percentage:.2f}%",
        f"<!-- 前十名发言人员共发言 {stats.top_n_total} 条，占总消息数的 {stats.top_n_percentage:.2f}% -->",
        "",
        "## 成员发言数量排名",
        "",
        "| 排名 | 成员昵称 | 微信ID | 发言数量 | 占比 | 累计占比 |",
        "| ---- | -------- | ------ | -------- | ---- | -------- |",
    ]

    for idx, member in enumerate(stats.members, start=1):
        lines.append(
            f"| {idx} | {member.nickname} | {member.wechat_id} | {member.count} | "
            f"{member.percentage:.2f}% | {member.cumulative_percentage:.2f}% |"
        )
    return "\n".join(lines).strip() + "\n"


def export_csv(path: Path, stats: MessageStats) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["排名", "成员昵称", "微信ID", "发言数量", "占比(%)", "累计占比(%)"])
        for idx, member in enumerate(stats.members, start=1):
            writer.writerow(
                [
                    idx,
                    member.nickname,
                    member.wechat_id,
                    member.count,
                    f"{member.percentage:.2f}",
                    f"{member.cumulative_percentage:.2f}",
                ]
            )


def export_xlsx(path: Path, stats: MessageStats) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    from openpyxl import Workbook  # Local import to avoid the dependency when unused

    wb = Workbook()
    ws = wb.active
    ws.title = "群消息统计"
    headers = ["排名", "成员昵称", "微信ID", "发言数量", "占比(%)", "累计占比(%)"]
    ws.append(headers)
    for idx, member in enumerate(stats.members, start=1):
        ws.append(
            [
                idx,
                member.nickname,
                member.wechat_id,
                member.count,
                round(member.percentage, 2),
                round(member.cumulative_percentage, 2),
            ]
        )
    for column_cells in ws.columns:
        max_length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
        column_letter = column_cells[0].column_letter
        ws.column_dimensions[column_letter].width = min(max_length + 2, 48)
    wb.save(path)


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
