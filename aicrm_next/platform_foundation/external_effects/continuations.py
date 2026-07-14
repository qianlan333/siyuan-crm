from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .models import ExternalEffectDispatchResult, ExternalEffectJob

ContinuationPredicate = Callable[[ExternalEffectJob, ExternalEffectDispatchResult], bool]
ContinuationHandler = Callable[[ExternalEffectJob, ExternalEffectDispatchResult], Mapping[str, Any]]


@dataclass(frozen=True)
class ExternalEffectContinuation:
    name: str
    matches: ContinuationPredicate
    run: ContinuationHandler


class ExternalEffectContinuationRegistry:
    def __init__(self, continuations: Iterable[ExternalEffectContinuation] = ()) -> None:
        registered = tuple(continuations)
        names = tuple(item.name for item in registered)
        if any(not name for name in names):
            raise ValueError("external effect continuation name is required")
        if len(set(names)) != len(names):
            raise ValueError("external effect continuation names must be unique")
        self._continuations = registered

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self._continuations)

    def run(self, job: ExternalEffectJob, dispatch_result: ExternalEffectDispatchResult) -> dict[str, Any]:
        for continuation in self._continuations:
            try:
                matches = continuation.matches(job, dispatch_result)
            except Exception as exc:
                return {
                    "applicable": True,
                    "ok": False,
                    "continuation": continuation.name,
                    "error": f"continuation predicate failed: {str(exc)[:500]}",
                }
            if not matches:
                continue
            try:
                result = dict(continuation.run(job, dispatch_result))
            except Exception as exc:
                return {
                    "applicable": True,
                    "ok": False,
                    "continuation": continuation.name,
                    "error": f"continuation handler failed: {str(exc)[:500]}",
                }
            return {
                "applicable": True,
                "continuation": continuation.name,
                **result,
            }
        return {"applicable": False, "reason": "no_registered_continuation"}


EMPTY_EXTERNAL_EFFECT_CONTINUATION_REGISTRY = ExternalEffectContinuationRegistry()
