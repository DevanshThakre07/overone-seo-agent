"""Run a fresh openai.com audit and compare it against the stored 482-issue run."""

from __future__ import annotations

import collections
import json
import sqlite3
import time

from app.tools.audit_tool import audit_site

OLD_AUDIT_ID = "429e090f-708b-41e4-a254-22ad4b2bdb3b"

started = time.time()
print("crawling https://openai.com/ (max_pages=50) ...", flush=True)
audit = audit_site("https://openai.com/", max_pages=50, save=True)
elapsed = time.time() - started

new_codes = collections.Counter(i.code for i in audit.issues)

db = sqlite3.connect("data/audits.db")
old_payload = next(
    p for (p,) in db.execute("select payload from audits where audit_id=?", (OLD_AUDIT_ID,))
)
old = json.loads(old_payload)
old_codes = collections.Counter(i["code"] for i in old["issues"])

print(f"\n{'='*72}")
print("PROOF OF FRESH RUN")
print(f"{'='*72}")
print(f"old audit_id : {OLD_AUDIT_ID}  ({old['created_at']})")
print(f"new audit_id : {audit.audit_id}  ({audit.created_at})")
print(f"crawl wall-clock: {elapsed:.1f}s")
print(f"pages crawled   : {audit.stats.pages_crawled}")
print(f"pages discovered: {audit.stats.pages_discovered}")

print(f"\n{'='*72}")
print("ISSUE COUNTS BY CODE")
print(f"{'='*72}")
print(f"{'code':<32}{'old':>7}{'new':>7}{'delta':>8}")
print("-" * 54)
for code in sorted(set(old_codes) | set(new_codes), key=lambda c: -old_codes.get(c, 0)):
    o, n = old_codes.get(code, 0), new_codes.get(code, 0)
    print(f"{code:<32}{o:>7}{n:>7}{n - o:>+8}")
print("-" * 54)
print(f"{'TOTAL':<32}{sum(old_codes.values()):>7}{sum(new_codes.values()):>7}"
      f"{sum(new_codes.values()) - sum(old_codes.values()):>+8}")

summary = audit.summary or {}
bd = summary.get("score_breakdown") or {}
print(f"\n{'='*72}")
print("SCORE")
print(f"{'='*72}")
print(f"old score : {old.get('score')}")
print(f"new score : {audit.score}")
print(f"status    : {summary.get('score_status')}")
print(f"mode      : {bd.get('scoring_mode')}  (min_pages={bd.get('min_pages_for_prevalence')})")
print(f"penalties : page={bd.get('page_level_penalty')} "
      f"(capped {bd.get('page_level_penalty_capped')}, cap_hit={bd.get('page_level_cap_hit')})  "
      f"site={bd.get('site_level_penalty')}  total={bd.get('total_penalty')}")

print("\nscored components:")
for c in bd.get("components", []):
    if c.get("scored"):
        print(f"  -{c['penalty']:>6.2f}  {c['code']:<30} "
              f"count={c['count']:<5} pages={c['pages_affected']:<4} "
              f"scope={c['scope']:<14} mode={c.get('mode','-')}")
print("informational (not scored):")
for c in bd.get("components", []):
    if not c.get("scored"):
        print(f"   {0.0:>6.2f}  {c['code']:<30} count={c['count']:<5} pages={c['pages_affected']}")

# Image alt evidence, straight off the fresh extraction.
tally = collections.Counter()
for page in audit.pages:
    for img in page.images:
        if img.is_source:
            tally["<source> skipped (no alt by spec)"] += 1
        elif img.decorative:
            tally['decorative alt=""/aria/pixel'] += 1
        elif not img.alt_present:
            tally["REAL missing alt"] += 1
        elif not str(img.alt).strip():
            tally["whitespace alt"] += 1
        else:
            tally["has alt text"] += 1

print(f"\n{'='*72}")
print(f"IMAGE ALT BREAKDOWN (fresh extraction, {sum(tally.values())} images)")
print(f"{'='*72}")
for k, v in tally.most_common():
    print(f"  {v:>5}  {k}")

alt_metrics = (audit.analyzer_results or {})
print("\nrendering:", json.dumps(summary.get("rendering", {}), default=str)[:300])
