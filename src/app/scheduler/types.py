"""调度执行过程中的数据载体（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


from ..models.model import Model


@dataclass
class IntervalPlan:
    fire_time: datetime
    window_start: datetime
    window_end: datetime

    def to_window_payload(self) -> dict:
        return {
            "start": self.window_start,
            "end": self.window_end,
            "time_str": f"{self.window_start.strftime('%Y-%m-%d %H:%M')}~{self.window_end.strftime('%Y-%m-%d %H:%M')}",
        }


@dataclass
class HtmlArtifactPlan:
    filename: str
    target_date: datetime
    generated_at: datetime


@dataclass
class GithubUploadArtifact:
    repo_path: str
    repo_full_name: str
    branch: str
    github_file_url: str
    pages_url: Optional[str] = None


@dataclass
class ModelSequenceItem:
    model: Model
    max_attempts: int


@dataclass
class AiSummaryResult:
    summary: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    model: Model
    prompt_meta: Dict[str, Any]
