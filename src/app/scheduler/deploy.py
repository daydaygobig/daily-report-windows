"""GitHub Pages 部署与 URL 构建（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote


from ..integrations import github
from ..integrations.security import decrypt_value
from ..models.execution import Execution
from ..models.job import Job

from .parsing import (
    _is_weekly_report,
)
from .types import (
    GithubUploadArtifact,
    HtmlArtifactPlan,
)

class DeployMixin:
    """HTML 日报上传 GitHub 与公开访问地址。"""

    async def _deploy_html_to_github(
        self,
        job: Job,
        execution: Execution,
        *,
        html_content: str,
        plan: HtmlArtifactPlan,
    ) -> GithubUploadArtifact:
        config = job.github_config
        if not config:
            raise RuntimeError("GitHub 配置缺失")
        token = decrypt_value(config.token_cipher)
        branch = (config.branch or "main").strip() or "main"
        filename = plan.filename if _is_weekly_report(job) else self._compose_html_report_archive_path(plan)
        relative_path = self._compose_content_path(config.path_prefix, filename)
        repo_full_name = f"{config.owner}/{config.repo}"
        pages_url = self._build_pages_url(config, relative_path)
        github_file_url = self._build_github_file_url(config, branch, relative_path)
        commit_message = f"feat: deploy job {job.id} execution {execution.id}"
        await github.upload_html_file(
            token=token,
            owner=config.owner,
            repo=config.repo,
            branch=branch,
            path=relative_path,
            content=html_content,
            commit_message=commit_message,
        )
        return GithubUploadArtifact(
            repo_path=relative_path,
            repo_full_name=repo_full_name,
            branch=branch,
            github_file_url=github_file_url,
            pages_url=pages_url,
        )

    @staticmethod
    def _compose_html_report_archive_path(plan: HtmlArtifactPlan) -> str:
        target_date = plan.target_date
        return f"{target_date.year}年/{target_date.year}年{target_date.month}月/{plan.filename}"

    @staticmethod
    def _compose_content_path(prefix: Optional[str], filename: str) -> str:
        normalized = (prefix or "").strip().strip("/ ")
        if normalized:
            return f"{normalized}/{filename}"
        return filename

    @staticmethod
    def _build_pages_url(config, relative_path: str) -> str:
        base = (config.pages_base_url or f"https://{config.owner}.github.io/{config.repo}/").strip()
        if not base.endswith("/"):
            base += "/"
        return f"{base}{relative_path}"

    @staticmethod
    def _build_github_file_url(config, branch: str, relative_path: str) -> str:
        encoded_branch = quote(branch.strip(), safe="")
        encoded_path = quote(relative_path.strip("/"), safe="/")
        return f"https://github.com/{config.owner}/{config.repo}/blob/{encoded_branch}/{encoded_path}"
