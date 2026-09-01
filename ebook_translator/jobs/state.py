"""Explicit translation-job lifecycle rules."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    DONE = "done"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


LEGAL_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.PAUSED,
            JobStatus.CANCELLED,
            JobStatus.DONE,
            JobStatus.FAILED,
            JobStatus.INTERRUPTED,
        }
    ),
    JobStatus.PAUSED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.INTERRUPTED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.FAILED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.DONE: frozenset(),
}


class IllegalJobTransition(ValueError):
    """Raised when a requested job transition violates the lifecycle contract."""


def parse_job_status(value: str | JobStatus) -> JobStatus:
    if isinstance(value, JobStatus):
        return value
    try:
        return JobStatus(value)
    except ValueError as error:
        raise IllegalJobTransition(f"Unknown job status: {value!r}") from error


def assert_job_transition(current: str | JobStatus, target: str | JobStatus) -> None:
    source = parse_job_status(current)
    destination = parse_job_status(target)
    if destination not in LEGAL_TRANSITIONS[source]:
        raise IllegalJobTransition(f"Illegal job transition: {source.value} -> {destination.value}")


def is_terminal(status: str | JobStatus) -> bool:
    value = parse_job_status(status)
    return value in {JobStatus.CANCELLED, JobStatus.DONE}
