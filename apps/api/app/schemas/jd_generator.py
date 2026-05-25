"""JD 生成器 Pydantic schemas。"""

from pydantic import BaseModel, Field


class JDGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="职位名称")
    requirements: str = Field(..., min_length=1, max_length=3000, description="核心要求")
    preferences: str | None = Field("", max_length=2000, description="偏好/补充说明")
    auto_improve: bool = Field(True, description="是否启用 Gen-Eval 迭代优化")


class JDIteration(BaseModel):
    iteration: int
    generated: str
    score: float | None = None
    feedback: str | None = None
    passed: bool = False


class JDGenerateResponse(BaseModel):
    success: bool = True
    data: str = ""
    iterations: list[dict] = []
    total_iterations: int = 0
    passed: bool = False


class JDImproveRequest(BaseModel):
    jd_content: str = Field(..., min_length=1, description="现有 JD 内容")
    feedback: str = Field(..., min_length=1, description="改进意见")


class JDImproveResponse(BaseModel):
    success: bool = True
    jd_content: str = ""
    original: str = ""
