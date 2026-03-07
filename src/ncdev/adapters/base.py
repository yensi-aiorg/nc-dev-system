from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ncdev.v2.models import CapabilityDescriptor, TaskExecutionRecord, TaskType


class ProviderVersionInfo(BaseModel):
    provider: str
    cli: str
    version: str = "unknown"


TaskExecutionResult = TaskExecutionRecord


class ProviderAdapter(ABC):
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def version_info(self) -> ProviderVersionInfo:
        raise NotImplementedError

    @abstractmethod
    def available_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self, model: str) -> CapabilityDescriptor:
        raise NotImplementedError

    @abstractmethod
    def supports_feature(self, feature_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def run_task(
        self,
        task_type: TaskType,
        artifact_path: Path,
        model: str,
        options: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        raise NotImplementedError
