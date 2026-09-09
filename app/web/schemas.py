"""Web 边界的数据契约；不改变 Pipeline 的 Stage Schema。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: 上传论文集的大小上限（UTF-8 字节），前端提示与后端校验共用。
MAX_UPLOAD_BYTES = 10_000_000
#: HTTP 请求体上限：JSON 转义与字段名会放大体积，留出余量后再按上传上限判空。
MAX_BODY_BYTES = 12_000_000


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=1000)
    research_questions: list[str] = Field(default_factory=list, max_length=20)
    filename: str = Field(max_length=200)
    content: str = Field(min_length=1, max_length=MAX_UPLOAD_BYTES)
    mode: Literal["generate", "dry_run"] = "generate"

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请填写研究主题")
        return value.strip()

    @field_validator("research_questions")
    @classmethod
    def validate_questions(cls, value: list[str]) -> list[str]:
        if any(len(question) > 2000 for question in value):
            raise ValueError("单个研究问题不得超过 2000 字")
        return [question.strip() for question in value if question.strip()]

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise ValueError(f"论文文件不得超过 {MAX_UPLOAD_BYTES // 1_000_000} MB")
        return value
