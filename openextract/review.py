"""Local review UI for the Pro confidence queue.

A minimal, dependency-free, server-rendered HTML page that lists fields the
confidence layer routed to a human, lets the human correct them, and applies
`record_correction` so the corrections feed back into the few-shot prompt.

Storage is in-memory (process-local). Self-hosted single-node is the target;
durable storage is a future concern.
"""
from __future__ import annotations

import html
import uuid
from collections import OrderedDict

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from .confidence import ConfidenceReport, record_correction

router = APIRouter()

# Bounded LRU-ish store: keep newest N reports so a long-running server doesn't
# leak memory. 500 is generous for a single self-hosted node.
_MAX_REPORTS = 500
_REPORTS: "OrderedDict[str, ConfidenceReport]" = OrderedDict()


def save_report(report: ConfidenceReport) -> str:
    report_id = str(uuid.uuid4())
    _REPORTS[report_id] = report
    while len(_REPORTS) > _MAX_REPORTS:
        _REPORTS.popitem(last=False)
    return report_id


def _layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
  body {{ font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 880px; margin: 2rem auto; padding: 0 1rem; color: #1c1f23; }}
  h1, h2 {{ font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th, td {{ text-align: left; padding: .55rem .7rem; border-bottom: 1px solid #eaecef; }}
  th {{ background: #f6f8fa; font-weight: 600; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; }}
  .pill.review {{ background: #fff5b8; color: #6a4f00; }}
  .pill.auto {{ background: #d6f5d6; color: #136b13; }}
  a {{ color: #0366d6; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  form {{ display: inline; }}
  input[type=text] {{ padding: 4px 6px; border: 1px solid #d0d7de; border-radius: 4px; font-size: 13px; }}
  button {{ padding: 4px 10px; border: 1px solid #d0d7de; background: #fff; border-radius: 4px; cursor: pointer; }}
  .muted {{ color: #6a737d; }}
</style></head><body>
<header><a href="/review">&larr; All reviews</a></header>
<h1>{html.escape(title)}</h1>
{body}
</body></html>"""


def _index_body() -> str:
    if not _REPORTS:
        return '<p class="muted">No reports yet. Submit a document to ' \
               '<code>POST /v1/extract-with-confidence</code> to create one.</p>'
    rows: list[str] = []
    # Newest first.
    for rid, rep in reversed(_REPORTS.items()):
        rows.append(
            f"<tr><td><a href='/review/{html.escape(rid)}'>{html.escape(rid[:8])}…</a></td>"
            f"<td>{len(rep.fields)}</td>"
            f"<td>{len(rep.review_queue)}</td>"
            f"<td>{rep.auto_accept_rate * 100:.0f}%</td>"
            f"<td>{rep.threshold:.0f}</td>"
            f"<td>{rep.samples}</td></tr>"
        )
    return ("<table><thead><tr><th>Report</th><th>Fields</th><th>In review</th>"
            "<th>Auto-accept</th><th>Threshold</th><th>Samples</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def _detail_body(report_id: str, rep: ConfidenceReport) -> str:
    rows: list[str] = []
    for f in rep.fields:
        pill_cls = "auto" if f.status == "auto_accept" else "review"
        if f.status == "review":
            action = (
                f"<form method='post' action='/review/{html.escape(report_id)}/correct'>"
                f"<input type='hidden' name='key' value='{html.escape(f.key)}'>"
                f"<input type='text' name='value' value='{html.escape(f.value)}' size='30'>"
                "<button type='submit'>Save</button></form>"
            )
        else:
            action = '<span class="muted">—</span>'
        agreement = "—" if f.agreement is None else f"{f.agreement:.0%}"
        rows.append(
            f"<tr><td>{html.escape(f.key)}</td>"
            f"<td>{html.escape(f.value)}</td>"
            f"<td>{f.confidence:.1f}</td>"
            f"<td>{agreement}</td>"
            f"<td><span class='pill {pill_cls}'>{html.escape(f.status)}</span></td>"
            f"<td>{action}</td></tr>"
        )
    summary = (
        f"<p class='muted'>Threshold {rep.threshold:.0f} · Samples {rep.samples} · "
        f"Auto-accept rate {rep.auto_accept_rate * 100:.0f}%</p>"
    )
    return summary + (
        "<table><thead><tr><th>Field</th><th>Value</th><th>Confidence</th>"
        "<th>Agreement</th><th>Status</th><th>Correct</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


@router.get("/review", response_class=HTMLResponse)
def review_index() -> HTMLResponse:
    return HTMLResponse(_layout("OpenExtract — Review queue", _index_body()))


@router.get("/review/{report_id}", response_class=HTMLResponse)
def review_detail(report_id: str) -> HTMLResponse:
    rep = _REPORTS.get(report_id)
    if rep is None:
        return HTMLResponse(_layout("Not found",
                                    "<p>No report with that id.</p>"), status_code=404)
    return HTMLResponse(_layout(f"Report {report_id[:8]}…",
                                _detail_body(report_id, rep)))


@router.post("/review/{report_id}/correct")
def review_correct(report_id: str, key: str = Form(...), value: str = Form(...)) -> RedirectResponse:
    rep = _REPORTS.get(report_id)
    if rep is None:
        return RedirectResponse(url="/review", status_code=303)
    record_correction(rep, key, value)
    return RedirectResponse(url=f"/review/{report_id}", status_code=303)
