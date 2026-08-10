from __future__ import annotations

import base64
from pathlib import Path

from app.config.settings import PROJECT_ROOT
from app.logging import get_logger, log_event
from app.models.audit import SiteAudit
from app.models.reports import ReportArtifact, ReportDocument, ReportFormat
from app.reports.builder import build_report_document
from app.reports.json_report import render_document_json, render_json
from app.reports.markdown_report import render_document_markdown, render_markdown
from app.reports.pdf_report import PdfNotImplementedError, render_pdf
from app.repositories.base import AuditRepository

logger = get_logger(__name__)


class ReportService:
    def __init__(self, repository: AuditRepository | None = None) -> None:
        self.repository = repository

    def build_document(self, audit: SiteAudit) -> ReportDocument:
        return build_report_document(audit)

    def generate(
        self,
        audit: SiteAudit,
        fmt: ReportFormat = ReportFormat.MARKDOWN,
        *,
        full_audit_json: bool = False,
        out_path: Path | str | None = None,
    ) -> ReportArtifact:
        document = build_report_document(audit)
        pdf_bytes: bytes | None = None

        if fmt == ReportFormat.JSON:
            content = (
                render_json(audit, full_audit=True)
                if full_audit_json
                else render_document_json(document)
            )
            metadata = {
                "seed_url": audit.seed_url,
                "score": f"{audit.score:.1f}",
                "pages": str(len(audit.pages)),
                "delivery": "inline_content",
                "media_type": "application/json",
                "content_encoding": "utf-8",
            }
        elif fmt == ReportFormat.MARKDOWN:
            content = render_markdown(audit)
            metadata = {
                "seed_url": audit.seed_url,
                "score": f"{audit.score:.1f}",
                "pages": str(len(audit.pages)),
                "delivery": "inline_content",
                "media_type": "text/markdown",
                "content_encoding": "utf-8",
            }
        elif fmt == ReportFormat.PDF:
            try:
                pdf_bytes = render_pdf(audit)
            except PdfNotImplementedError:
                raise
            content = base64.b64encode(pdf_bytes).decode("ascii")
            metadata = {
                "seed_url": audit.seed_url,
                "score": f"{audit.score:.1f}",
                "pages": str(len(audit.pages)),
                "delivery": "inline_content",
                "media_type": "application/pdf",
                "content_encoding": "base64",
                "byte_length": str(len(pdf_bytes)),
            }
        else:
            raise ValueError(f"Unsupported report format: {fmt}")

        artifact = ReportArtifact(
            audit_id=audit.audit_id,
            format=fmt,
            content=content,
            document=document,
            metadata=metadata,
        )

        if out_path is not None:
            artifact = self.write(artifact, Path(out_path), pdf_bytes=pdf_bytes)

        log_event(
            logger,
            "report_generated",
            audit_id=audit.audit_id,
            format=fmt.value,
            path=artifact.path,
        )
        return artifact

    def generate_from_audit_id(
        self,
        audit_id: str,
        fmt: ReportFormat = ReportFormat.MARKDOWN,
        *,
        out_path: Path | str | None = None,
    ) -> ReportArtifact:
        if self.repository is None:
            raise ValueError("Repository is required to load audits by id")
        audit = self.repository.get(audit_id)
        if audit is None:
            raise KeyError(f"Audit not found: {audit_id}")
        return self.generate(audit, fmt, out_path=out_path)

    def pdf_bytes(self, artifact: ReportArtifact) -> bytes:
        if artifact.format != ReportFormat.PDF:
            raise ValueError("Artifact is not a PDF")
        if artifact.metadata.get("content_encoding") == "base64":
            return base64.b64decode(artifact.content)
        raise ValueError("PDF artifact missing base64 content")

    def write(
        self,
        artifact: ReportArtifact,
        path: Path,
        *,
        pdf_bytes: bytes | None = None,
    ) -> ReportArtifact:
        path = Path(path)
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        if artifact.format == ReportFormat.PDF:
            raw = pdf_bytes
            if raw is None:
                raw = self.pdf_bytes(artifact)
            path.write_bytes(raw)
        else:
            path.write_text(artifact.content, encoding="utf-8")

        try:
            artifact.path = str(path.relative_to(PROJECT_ROOT))
        except ValueError:
            artifact.path = path.name
        artifact.metadata["delivery"] = "file_and_inline_content"
        artifact.metadata["relative_path"] = artifact.path or ""
        return artifact


def default_pdf_out_path(audit_id: str) -> Path:
    return PROJECT_ROOT / "data" / "reports" / f"{audit_id}.pdf"
