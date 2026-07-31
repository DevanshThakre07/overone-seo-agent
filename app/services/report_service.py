from __future__ import annotations

from pathlib import Path

from app.logging import get_logger, log_event
from app.models.audit import SiteAudit
from app.models.reports import ReportArtifact, ReportDocument, ReportFormat
from app.reports.builder import build_report_document
from app.reports.json_report import render_document_json, render_json
from app.reports.markdown_report import render_document_markdown
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

        if fmt == ReportFormat.JSON:
            content = (
                render_json(audit, full_audit=True)
                if full_audit_json
                else render_document_json(document)
            )
        elif fmt == ReportFormat.MARKDOWN:
            content = render_document_markdown(document)
        elif fmt == ReportFormat.PDF:
            try:
                raw = render_pdf(audit)
            except PdfNotImplementedError:
                raise
            content = raw.decode("latin-1")  # unreachable until PDF exists
        else:
            raise ValueError(f"Unsupported report format: {fmt}")

        artifact = ReportArtifact(
            audit_id=audit.audit_id,
            format=fmt,
            content=content,
            document=document,
            metadata={
                "seed_url": audit.seed_url,
                "score": f"{audit.score:.1f}",
                "pages": str(len(audit.pages)),
            },
        )

        if out_path is not None:
            artifact = self.write(artifact, Path(out_path))

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

    def write(self, artifact: ReportArtifact, path: Path) -> ReportArtifact:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")
        artifact.path = str(path)
        return artifact
