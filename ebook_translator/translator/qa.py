"""Deterministic translation QA rules for local workbench inspection.

Wing: code | Topic: qa | Updated: 2026-10-08 19:11
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ebook_translator.models import GlossaryEntry


@dataclass(frozen=True)
class QAIssue:
    """Biểu diễn một lỗi hoặc cảnh báo QA được phát hiện trong quá trình kiểm tra bản dịch.

    Attributes:
        code: Mã định danh quy tắc QA.
        severity: Mức độ nghiêm trọng ("error" hoặc "warning").
        message: Thông báo mô tả chi tiết vấn đề QA.
        expected: Giá trị kỳ vọng.
        actual: Giá trị thực tế nhận được.
    """

    code: str
    severity: str
    message: str
    expected: str = ""
    actual: str = ""


@dataclass(frozen=True)
class QAResult:
    """Kết quả kiểm tra QA chứa danh sách các vấn đề được phát hiện.

    Attributes:
        issues: Tuple các đối tượng QAIssue thu được từ quá trình kiểm tra.
    """

    issues: tuple[QAIssue, ...]

    @property
    def passed(self) -> bool:
        """Kiểm tra bản dịch có đạt tiêu chuẩn hay không.

        Returns:
            True nếu không có vấn đề nào có severity là "error", ngược lại False.
        """
        return not any(issue.severity == "error" for issue in self.issues)


def _numbers(text: str) -> list[str]:
    return re.findall(r"(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?)(?!\w)", text)


def check_translation(
    source: str,
    translated: str,
    glossary: list[GlossaryEntry] | None = None,
) -> QAResult:
    """Kiểm tra chất lượng bản dịch dựa trên các quy tắc QA cố định.

    Args:
        source: Chuỗi văn bản nguồn.
        translated: Chuỗi văn bản đã dịch.
        glossary: Danh sách thuật ngữ GlossaryEntry cần kiểm tra tuân thủ (tùy chọn).

    Returns:
        QAResult chứa danh sách các QAIssue phát hiện được.
    """
    issues: list[QAIssue] = []
    source_clean = source.strip()
    translated_clean = translated.strip()

    if source_clean and not translated_clean:
        issues.append(
            QAIssue(
                code="missing_translation",
                severity="error",
                message="Source text is non-empty but translation is empty.",
            )
        )
        return QAResult(tuple(issues))

    source_numbers = _numbers(source_clean)
    translated_numbers = _numbers(translated_clean)
    if source_numbers != translated_numbers:
        issues.append(
            QAIssue(
                code="number_mismatch",
                severity="warning",
                message="Numeric values differ between source and translation.",
                expected=" | ".join(source_numbers),
                actual=" | ".join(translated_numbers),
            )
        )

    if source_clean and translated_clean and source_clean.casefold() == translated_clean.casefold():
        issues.append(
            QAIssue(
                code="source_residue",
                severity="warning",
                message="Translation is identical to the source text.",
            )
        )

    for entry in glossary or []:
        source_term = entry.source_term.strip()
        target_term = entry.target_term.strip()
        if not source_term or not target_term:
            continue
        if source_term.casefold() in source_clean.casefold() and target_term not in translated_clean:
            issues.append(
                QAIssue(
                    code="glossary_violation",
                    severity="error",
                    message=f"Required glossary term is missing: {target_term}",
                    expected=target_term,
                )
            )

    if source_clean and translated_clean:
        ratio = len(translated_clean) / max(1, len(source_clean))
        if ratio < 0.25 or ratio > 4.0:
            issues.append(
                QAIssue(
                    code="length_anomaly",
                    severity="warning",
                    message="Translation length is unusually different from source length.",
                    expected="0.25x–4.0x source length",
                    actual=f"{ratio:.2f}x",
                )
            )

    return QAResult(tuple(issues))
