"""AI 初筛 Pydantic schemas — 流水线 + 聚合评估。"""

from pydantic import BaseModel, Field


class ScreeningRequest(BaseModel):
    candidate_id: str = Field(..., description="候选人 ID")
    job_id: str = Field(..., description="职位 ID")
    resume_text: str = Field(..., min_length=1, description="简历文本")
    job_requirements: str = Field(..., min_length=1, description="职位要求文本")


class ScreeningResult(BaseModel):
    success: bool = True
    pipeline_id: str = ""
    candidate_id: str = ""
    job_id: str = ""
    overall_score: float = 0.0
    dimensions: dict = {}
    parsed_resume: dict = {}
    gate_passed: bool = False
    needs_human_review: bool = False
    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendation: str = ""
    summary: str = ""
    steps: list[dict] = []


class PipelineProgress(BaseModel):
    pipeline_id: str = ""
    status: str = "running"
    progress: float = 0.0
    current_step: str = ""
    steps: list[dict] = []


class MatchDimension(BaseModel):
    name: str
    score: float
    analysis: str


class MultiEvaluateRequest(BaseModel):
    candidate_info: str = Field(..., description="候选人完整信息")
    dimensions: list[str] | None = Field(None, description="评估维度列表")


class MultiEvaluateResponse(BaseModel):
    success: bool = True
    dimension_results: list[dict] = []
    consensus: dict = {}
    total_dimensions: int = 0


class HumanLoopRequest(BaseModel):
    action_type: str = Field("schedule_interview", description="操作类型")
    params: dict = Field(default_factory=dict, description="操作参数")
    confirm: bool = False
    approval_id: str | None = None
    approved: bool = False
    feedback: str | None = None


class HumanLoopResponse(BaseModel):
    success: bool = True
    status: str = ""
    approval: dict = {}
