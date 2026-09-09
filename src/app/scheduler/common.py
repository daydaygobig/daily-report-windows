"""调度器各拆分模块共享的运行时单例与常量（避免相互依赖 service.py 造成循环导入）。"""

from ..config import get_settings
from ..repositories.job_repo import JobRepository
from ..repositories.webhook_repo import WebhookRepository

settings = get_settings()
job_repo = JobRepository()
webhook_repo = WebhookRepository()

EMPTY_CHATLOG_ERROR_MESSAGE = "聊天记录多次拉取为空，疑似指定时间段内无聊天信息"

# 上游日报注入：卡片任务只认这个时间窗内成功完成的日报，防止把几天前的话题清单塞进今天的聊天记录。
UPSTREAM_MAX_AGE_HOURS = 24
UPSTREAM_MAX_TOPICS = 12
