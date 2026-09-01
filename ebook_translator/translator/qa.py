"""Deterministic translation QA rules for local workbench inspection."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ebook_translator.models import GlossaryEntry


@dataclass(frozen=True)
class QAIssue:
    code: str
    severity: str
    message: str
    expected: str = ""
    actual: str = ""


@dataclass(frozen=True)
class QAResult:
    issues: tuple[QAIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def _numbers(text: str) -> list[str]:
    return re.findall(r"(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?)(?!\w)", text)


def check_translation(
    source: str,
    translated: str,
    glossary: list[GlossaryEntry] | None = None,
) -> QAResult:
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
