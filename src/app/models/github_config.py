"""GitHub deployment configuration."""

from sqlalchemy import Boolean, Column, String, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class GithubConfig(BaseModel):
    __tablename__ = "github_configs"

    name = Column(String(120), nullable=False, unique=True)
    owner = Column(String(120), nullable=False)
    repo = Column(String(120), nullable=False)
    branch = Column(String(80), nullable=False, default="main")
    path_prefix = Column(String(255), nullable=True)
    filename_template = Column(String(255), nullable=False, default="新茧群日报_{YYYY-MM-DD}.html")
    token_cipher = Column(Text, nullable=False)
    pages_base_url = Column(String(255), nullable=True)
    view_url_mode = Column(String(40), nullable=False, default="github_pages")
    view_url_template = Column(Text, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)

    jobs = relationship("Job", back_populates="github_config", foreign_keys="Job.github_config_id")
