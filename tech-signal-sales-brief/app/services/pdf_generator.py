"""Convert markdown brief output to a styled PDF report."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import markdown2
from weasyprint import HTML

logger = logging.getLogger(__name__)

CSS = """
@page {
    size: A4;
    margin: 2cm 2.5cm;
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9px;
        color: #888;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
}

body {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #1a1a1a;
}

/* Cover / header block */
.report-header {
    border-bottom: 3px solid #1a73e8;
    padding-bottom: 20px;
    margin-bottom: 30px;
}

.report-header h1 {
    font-size: 24pt;
    color: #1a73e8;
    margin: 0 0 6px 0;
    font-weight: 700;
}

.report-header .subtitle {
    font-size: 13pt;
    color: #555;
    margin: 0 0 4px 0;
}

.report-header .date {
    font-size: 10pt;
    color: #888;
}

/* Headings */
h1 { font-size: 20pt; color: #1a73e8; margin-top: 30px; border-bottom: 2px solid #e8eaed; padding-bottom: 6px; }
h2 { font-size: 16pt; color: #1a73e8; margin-top: 24px; }
h3 { font-size: 13pt; color: #333; margin-top: 18px; }
h4 { font-size: 11pt; color: #555; margin-top: 14px; }

/* Body text */
p { margin: 8px 0; }
ul, ol { margin: 8px 0 8px 20px; }
li { margin: 4px 0; }

/* Bold emphasis */
strong { color: #1a1a1a; }

/* Code / technical terms */
code {
    background: #f1f3f4;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 10pt;
    font-family: 'Consolas', 'Courier New', monospace;
}

pre {
    background: #f8f9fa;
    border: 1px solid #e8eaed;
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 9.5pt;
    overflow-x: auto;
}

/* Horizontal rules — section dividers */
hr {
    border: none;
    border-top: 2px solid #e8eaed;
    margin: 28px 0;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 10pt;
}
th {
    background: #1a73e8;
    color: white;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
}
td {
    padding: 8px 12px;
    border-bottom: 1px solid #e8eaed;
}
tr:nth-child(even) td { background: #f8f9fa; }

/* Blockquotes — callout boxes */
blockquote {
    border-left: 4px solid #1a73e8;
    background: #e8f0fe;
    padding: 12px 16px;
    margin: 16px 0;
    border-radius: 0 6px 6px 0;
    font-style: normal;
}
blockquote p { margin: 4px 0; }
"""


def generate_pdf(
    markdown_content: str,
    schedule_name: str,
    report_date: datetime | None = None,
) -> bytes:
    """Convert markdown content to a styled PDF.

    Args:
        markdown_content: The markdown text from the brief generator agent.
        schedule_name: Display name for the report (e.g. "AI/ML & Agents").
        report_date: Timestamp for the report header. Defaults to now (UTC).

    Returns:
        PDF file content as bytes.
    """
    if report_date is None:
        report_date = datetime.now(timezone.utc)

    html_body = markdown2.markdown(
        markdown_content,
        extras=["tables", "fenced-code-blocks", "header-ids", "break-on-newline"],
    )

    header = f"""
    <div class="report-header">
        <h1>Tech Signal Intelligence Report</h1>
        <p class="subtitle">{schedule_name}</p>
        <p class="date">Generated: {report_date.strftime('%B %d, %Y at %H:%M UTC')}</p>
    </div>
    """

    full_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
{header}
{html_body}
</body>
</html>"""

    pdf_bytes = HTML(string=full_html).write_pdf()
    logger.info("Generated PDF: %.1f KB", len(pdf_bytes) / 1024)
    return pdf_bytes


def save_pdf(pdf_bytes: bytes, output_dir: str | Path, filename: str) -> Path:
    """Write PDF bytes to disk and return the file path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_bytes(pdf_bytes)
    logger.info("Saved PDF to %s", path)
    return path
