"""Explicit translation-job lifecycle rules.

Updated: 2026-10-08 19:16
"""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Enum biểu diễn các trạng thái vòng đời của tác vụ dịch."""

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
    """Chuyển đổi chuỗi hoặc JobStatus sang đối tượng JobStatus hợp lệ.

    Args:
        value: Chuỗi giá trị hoặc đối tượng JobStatus.

    Returns:
        Đối tượng JobStatus tương ứng với đầu vào.

    Raises:
        IllegalJobTransition: Nếu giá trị đầu vào không phải là trạng thái hợp lệ.
    """
    if isinstance(value, JobStatus):
        return value
    try:
        return JobStatus(value)
    except ValueError as error:
        raise IllegalJobTransition(f"Unknown job status: {value!r}") from error


def assert_job_transition(current: str | JobStatus, target: str | JobStatus) -> None:
    """Kiểm tra tính hợp lệ của việc chuyển trạng thái tác vụ.

    Args:
        current: Trạng thái hiện tại của tác vụ.
        target: Trạng thái đích muốn chuyển tới.

    Raises:
        IllegalJobTransition: Nếu việc chuyển từ current sang target vi phạm quy tắc chuyển trạng thái.
    """
    source = parse_job_status(current)
    destination = parse_job_status(target)
    if destination not in LEGAL_TRANSITIONS[source]:
        raise IllegalJobTransition(f"Illegal job transition: {source.value} -> {destination.value}")


def is_terminal(status: str | JobStatus) -> bool:
    """Kiểm tra xem trạng thái tác vụ có phải là trạng thái kết thúc hay không.

    Args:
        status: Trạng thái tác vụ dạng chuỗi hoặc JobStatus.

    Returns:
        True nếu trạng thái là CANCELLED hoặc DONE, ngược lại trả về False.
    """
    value = parse_job_status(status)
    return value in {JobStatus.CANCELLED, JobStatus.DONE}
