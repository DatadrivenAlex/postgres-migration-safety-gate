"""Explainable, offline PostgreSQL migration checks.

This deliberately combines SQL parsing with conservative pattern checks; it never connects to a DB.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

import sqlglot
from sqlglot.errors import ParseError

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    statement: int
    message: str
    recommendation: str
    excerpt: str


@dataclass(frozen=True)
class Analysis:
    parsed_statements: int
    findings: tuple[Finding, ...]

    @property
    def blocked(self) -> bool:
        return any(item.severity == "error" for item in self.findings)

    def to_dict(self) -> dict:
        return {
            "parsed_statements": self.parsed_statements,
            "blocked": self.blocked,
            "findings": [asdict(item) for item in self.findings],
        }


RULES = {
    "PG001": "Destructive object removal",
    "PG002": "Column removal",
    "PG003": "New required column",
    "PG004": "Column type change",
    "PG005": "Non-concurrent index build",
    "PG006": "Concurrent index inside transaction",
    "PG007": "Constraint validation lock risk",
    "PG008": "Non-concurrent index removal",
    "PG009": "Column rename deployment risk",
    "PG010": "Immediate NOT NULL validation",
}


def _excerpt(sql: str) -> str:
    compact = " ".join(sql.strip().split())
    return compact[:180] + ("…" if len(compact) > 180 else "")


def _finding(
    rule: str, severity: Severity, n: int, message: str, recommendation: str, sql: str
) -> Finding:
    return Finding(rule, severity, n, message, recommendation, _excerpt(sql))


def analyze(sql: str) -> Analysis:
    if not isinstance(sql, str):
        raise TypeError("sql must be text")
    try:
        parsed = sqlglot.parse(sql, read="postgres")
    except ParseError as exc:
        return Analysis(
            0,
            (
                _finding(
                    "PG000",
                    "error",
                    0,
                    f"SQL parse failed: {str(exc).splitlines()[0]}",
                    "Fix the SQL syntax before review.",
                    sql,
                ),
            ),
        )

    statements = [
        (i, statement.sql(dialect="postgres"))
        for i, statement in enumerate(parsed, start=1)
        if statement
    ]
    explicit_transaction = any(
        re.match(r"^\s*(BEGIN|START\s+TRANSACTION)\b", text, re.IGNORECASE)
        for _, text in statements
    )
    findings: list[Finding] = []
    for n, text in statements:
        upper = text.upper()
        if re.search(r"\bDROP\s+(TABLE|SCHEMA|TYPE|DATABASE|COLUMN)\b", upper):
            findings.append(
                _finding(
                    "PG001",
                    "error",
                    n,
                    "Dropping a database object can remove production data.",
                    "Use a staged deprecation and verify backups and dependents before removal.",
                    text,
                )
            )
        if re.search(r"\bALTER\s+TABLE\b.*\bDROP\s+COLUMN\b", upper, re.DOTALL):
            findings.append(
                _finding(
                    "PG002",
                    "error",
                    n,
                    "Dropping a column is not safe during a rolling deploy if any version still reads it.",
                    "Deploy code that stops using the column first; remove it in a later migration.",
                    text,
                )
            )
        if (
            re.search(r"\bALTER\s+TABLE\b", upper)
            and re.search(r"\bADD\s+COLUMN\b", upper)
            and re.search(r"\bNOT\s+NULL\b", upper)
            and not re.search(r"\bDEFAULT\b", upper)
        ):
            findings.append(
                _finding(
                    "PG003",
                    "warning",
                    n,
                    "A new NOT NULL column without a default leaves existing rows unresolved.",
                    "Add it nullable, backfill in batches, then validate and enforce NOT NULL separately.",
                    text,
                )
            )
        if re.search(
            r"\bALTER\s+TABLE\b.*\bALTER\s+(?:COLUMN\s+\S+\s+)?(?:SET\s+DATA\s+)?TYPE\b",
            upper,
            re.DOTALL,
        ):
            findings.append(
                _finding(
                    "PG004",
                    "warning",
                    n,
                    "Changing a column type may rewrite the table and hold a strong lock.",
                    "Check PostgreSQL's cast and table size; consider an additive column and batched backfill.",
                    text,
                )
            )
        if re.search(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", upper) and not re.search(
            r"\bCONCURRENTLY\b", upper
        ):
            findings.append(
                _finding(
                    "PG005",
                    "warning",
                    n,
                    "A regular index build can block writes while it runs.",
                    "For a live table, consider CREATE INDEX CONCURRENTLY in its own non-transactional migration.",
                    text,
                )
            )
        if (
            re.search(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+CONCURRENTLY\b", upper)
            and explicit_transaction
        ):
            findings.append(
                _finding(
                    "PG006",
                    "error",
                    n,
                    "PostgreSQL does not allow CREATE INDEX CONCURRENTLY inside a transaction block.",
                    "Run the concurrent index statement in a migration configured without a transaction.",
                    text,
                )
            )
        if re.search(
            r"\bADD\s+(?:CONSTRAINT\s+\S+\s+)?(?:FOREIGN\s+KEY|CHECK)\b", upper
        ) and not re.search(r"\bNOT\s+VALID\b", upper):
            findings.append(
                _finding(
                    "PG007",
                    "warning",
                    n,
                    "Adding a validated constraint may scan existing rows and increase lock time.",
                    "Consider adding it NOT VALID, then validating it separately after backfill.",
                    text,
                )
            )
        if re.search(r"\bDROP\s+INDEX\b", upper) and not re.search(r"\bCONCURRENTLY\b", upper):
            findings.append(
                _finding(
                    "PG008",
                    "warning",
                    n,
                    "Dropping an index without CONCURRENTLY can block writes.",
                    "Consider DROP INDEX CONCURRENTLY outside a transaction when the index is not needed.",
                    text,
                )
            )
        if re.search(r"\bRENAME\s+COLUMN\b", upper):
            findings.append(
                _finding(
                    "PG009",
                    "warning",
                    n,
                    "Renaming a column can break old and new application versions during rollout.",
                    "Use an expand-migrate-contract sequence: add, dual-write/read, backfill, then remove later.",
                    text,
                )
            )
        if re.search(r"\bALTER\s+TABLE\b", upper) and re.search(r"\bSET\s+NOT\s+NULL\b", upper):
            findings.append(
                _finding(
                    "PG010",
                    "warning",
                    n,
                    "Setting NOT NULL can require a table scan and a strong lock.",
                    "Pre-validate with a CHECK constraint where supported, then enforce after validating existing rows.",
                    text,
                )
            )

    return Analysis(len(statements), tuple(findings))
