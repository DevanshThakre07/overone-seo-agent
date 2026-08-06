"""Compare scoring variants against saved audits.

Columns:
  stored     score as recorded in the saved audit JSON
  prev-only  prevalence weighting with no sample-size threshold
  threshold  prevalence weighting gated on min_pages_for_prevalence
"""

from __future__ import annotations

import json
import sqlite3

from app.analyzers.scorer import compute_score_breakdown
from app.config.settings import get_settings
from app.models.issues import Issue

scoring = get_settings().analyzer.scoring
no_threshold = scoring.model_copy(update={"min_pages_for_prevalence": 1})

print(
    f"prevalence_scale={scoring.prevalence_scale}  "
    f"cap={scoring.max_page_level_penalty}  "
    f"min_pages_for_prevalence={scoring.min_pages_for_prevalence}\n"
)

header = f"{'url':<20}{'pages':>6}{'issues':>8}{'stored':>8}{'prev-only':>11}{'threshold':>11}  mode"
print(header)
print("-" * len(header))

db = sqlite3.connect("data/audits.db")
query = "select seed_url, score, payload from audits order by created_at"

for seed_url, stored, payload in db.execute(query):
    data = json.loads(payload)
    if "issues" not in data:
        continue
    pages = data.get("pages_analyzed") or len(data.get("pages", [])) or 1
    issues = [Issue(**i) for i in data["issues"]]

    old = compute_score_breakdown(issues, no_threshold, pages_analyzed=pages)
    new = compute_score_breakdown(issues, scoring, pages_analyzed=pages)

    url = (seed_url or "?").replace("https://", "")[:20]
    stored_txt = f"{stored:.1f}" if isinstance(stored, (int, float)) else "n/a"
    print(
        f"{url:<20}{pages:>6}{len(issues):>8}{stored_txt:>8}"
        f"{old['score']:>11.1f}{new['score']:>11.1f}  {new['scoring_mode']}"
    )
