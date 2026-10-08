from __future__ import annotations

from functools import lru_cache

from ..services.analysis_service import AnalysisService
from ..services.storage_service import JsonResultStore


@lru_cache(maxsize=1)
def get_store() -> JsonResultStore:
    return JsonResultStore()


@lru_cache(maxsize=1)
def get_service() -> AnalysisService:
    return AnalysisService(get_store())
