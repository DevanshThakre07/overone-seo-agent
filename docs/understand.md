# SEO Agent Dashboard — Beginner Guide

Plain-English descriptions of every control and section on the dashboard.  
Nothing here invents data — empty panels mean that signal was not run or is unavailable.

**In the live UI:** every section has a small **i** button. Click it for “What is this?”, “What should I do?”, and a tip.

**Dashboard layout (quality UX):**
1. **How to get a high-quality report** — 4-step path at the top  
2. Sticky controls — URL / API key / Load / Run audit  
3. **Advanced actions** (collapsed) — rank tracker, placement, schedules  
4. Results in zones: Overview → Demand & traffic → Competitive → On-page → Technical → Delivery  
5. Each panel shows **Ready / Partial / Not run / Provisional** so empty never looks like success  

**Dashboard URL (local):** `http://localhost:8000/dashboard/ui?url=https://example.com/`

---

## Top controls (not report panels)

| Control | Plain English |
|--------|----------------|
| **Site URL** | The website you’re auditing. |
| **Google account_id** | Your Connect Google nickname (e.g. `demo`) so GSC/GA4 can load. |
| **API key** | Password so the server allows audits (from `SEO-Agent/.env` → `SEO_API_KEY`). |
| **GA4 property** | Which Analytics property to pull traffic from. |
| **Load dashboard** | Show the last saved results for this URL. |
| **Run audit** | Crawl the site again and refresh the report. |
| **Get optimize advice** | AI suggests better title/meta/H1 (does **not** change your live site). |
| **Keyword position tracker** | Asks Google: “Where do I rank for these words?” (paid DataForSEO). Fills **Rank check**, **SERP**, and **Rank history**. |
| **Get keyword placement** | Looks at your **page**: “Where should this word appear — title, H1, body?” Different from ranking. |
| **Schedules (assign)** | Create a recurring audit (every N hours), pause/resume/delete from the Schedules panel. |
| **Audit options** | Extra switches: how many pages, PageSpeed, GA4, backlinks, auth crawl, etc. |
| **Crawl presets** | Quick (3 pages) / Standard (15, default) / Deep (50). |

---

## Main result panels

| Section | What it is (beginner) | Good / bad look like |
|--------|------------------------|----------------------|
| **Site audit** | Overall SEO health score for the crawl. | Higher score = healthier. Critical/warning counts = problems to fix. |
| **PageSpeed / CWV** | How fast the page feels (Google lab test). | Low score / slow LCP = users and Google may bounce. |
| **Search Console** | Real Google Search data: queries, clicks, impressions. | Shows what people actually search to find you. |
| **Google Analytics** | Real traffic: sessions, users, top pages. | How many people visit after they find you. |
| **Score trends** | Your audit score over time (bars). | Up = improving; down = getting worse. |
| **Audit history** | List of past saved audits. | Compare “last week vs today.” |
| **Top issues** | Concrete problems found (titles, canonicals, etc.). | Fix critical first, then warnings. |
| **Recommendations** | Suggested next actions with rewrite ideas. Each action should cite **evidence** (URL + field + current/suggested) — we don’t invent missing tags that are already on the page. | A to-do list grounded in what was crawled. |
| **Keyword research** | Search volume, difficulty, CPC, competition, related ideas, light intent hint. | “Is this keyword worth targeting?” |
| **SERP** | Who currently ranks #1, #2, #3… for your keywords. | Your competitors on Google for that query. |
| **Rank check** | **Your** position for each keyword right now. | Position number = ranking; “not ranking” = not in checked results. |
| **Rank history** | Same rank check over time **with dates**. | See if you’re moving up/down across days. |
| **Backlinks** | Other sites linking to you (+ spam risk). | Needs DataForSEO balance; **402 Payment Required** = top up the account. |
| **Optimize advice** | AI rewrite suggestions for title/meta/H1. | Copy ideas — does not edit your live site. |
| **Keyword placement** | On **your page**, which slots already have the keyword / which are missing. | Use **Get keyword placement**, not the position tracker. |
| **Login wall** | Does this URL look locked behind login? | Useful for private apps. |
| **Auth crawl** | Did we crawl with your cookie/token? | Only if you enabled authenticated crawl. |
| **Rendering** | Did we need JavaScript (Playwright) to see content? | SPAs often need this. |
| **Analyzers** | Each SEO check that ran. Open a row to see exact issues (code, message, page). | Counts + drill-down. Details also appear in Top issues. |
| **Schedules** | Auto re-audits on a timer. | Empty = none set up. |
| **Report / share** | Download PDF or **Create client scorecard link** (public `/share/{token}` — score + top issues; no API key for viewers). | What you send a client. |
| **Compare audits** | Diff between two saved runs. | Needs 2+ audits. |

---

## Rank history — how to read it

Example you might see:

- **learning** / **actoro** — **4 checks**
- **books** / **action** — **1 check**
- Trail like `— → — → —`

**What that means**

- Each **check** is one time we asked Google (via DataForSEO) where your site ranks for that keyword.
- More checks = more history over time.
- A trail of `—` means: **no ranking position found** in the results we pulled (not a chart of #1 → #2).
- “1 check” means we only looked once so far — not enough to show a trend yet.

Plain English:  
“We looked several times for these keywords; if you only see dashes, your site was not in the top results for those runs.”

---

## Two keyword features people mix up

| Feature | Button / control | Question it answers |
|--------|------------------|---------------------|
| **Position tracker** | **Activate position tracker** + **Check positions** | “Where do I rank on **Google**?” |
| **Keyword placement** | **Get keyword placement** | “Where should this word sit on **my page**?” |

Activating one never fills the other.

---

## Quick “what should I look at first?”

1. **Site audit** score + **Top issues**  
2. **Search Console** + **Google Analytics** (real users)  
3. **Rank check** if you care about Google positions  
4. **Keyword placement** if you care about on-page wording  
5. Skip **Backlinks** until DataForSEO is topped up (avoid 402 errors)

---

## Related docs

- Product roadmap: `docs/planning.md`  
- Google Search Console / OAuth: `docs/GOOGLE_SEARCH_CONSOLE.md`  
- Hosting: `docs/HOSTING.md`
