from app.schemas.common import Message, PaginationMeta, ListResponse
from app.schemas.candidate import CandidateCreate, CandidateRead, CandidateUpdate
from app.schemas.job import JobCreate, JobRead, JobUpdate
from app.schemas.screening import (
    ScreeningRequest, ScreeningResult, PipelineProgress, MatchDimension,
    MultiEvaluateRequest, MultiEvaluateResponse,
    HumanLoopRequest, HumanLoopResponse,
)
from app.schemas.jd_generator import JDGenerateRequest, JDGenerateResponse, JDImproveRequest, JDImproveResponse
from app.schemas.auth import (
    LoginRequest, RegisterRequest, TokenResponse, UserResponse, UserUpdateRequest,
)
from app.schemas.knowledge import (
    DocumentUploadRequest, DocumentRead, KnowledgeQueryRequest,
    KnowledgeQueryResponse, KnowledgeSearchResult, DocumentIngestResponse,
)
from app.schemas.application import ApplicationCreate, ApplicationRead, ApplicationUpdate, ApplicationListRead
from app.schemas.setting import SettingCreate, SettingRead, SettingUpdate

__all__ = [
    "Message", "PaginationMeta", "ListResponse",
    "LoginRequest", "RegisterRequest", "TokenResponse", "UserResponse", "UserUpdateRequest",
    "CandidateCreate", "CandidateRead", "CandidateUpdate",
    "JobCreate", "JobRead", "JobUpdate",
    "ScreeningRequest", "ScreeningResult", "PipelineProgress", "MatchDimension",
    "MultiEvaluateRequest", "MultiEvaluateResponse",
    "HumanLoopRequest", "HumanLoopResponse",
    "JDGenerateRequest", "JDGenerateResponse", "JDImproveRequest", "JDImproveResponse",
    "DocumentUploadRequest", "DocumentRead", "KnowledgeQueryRequest",
    "KnowledgeQueryResponse", "KnowledgeSearchResult", "DocumentIngestResponse",
    "ApplicationCreate", "ApplicationRead", "ApplicationUpdate", "ApplicationListRead",
    "SettingCreate", "SettingRead", "SettingUpdate",
]
