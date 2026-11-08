"""Build the static portfolio site into dist/ (Python standard library only).

    python3 build.py            # -> dist/
    python3 -m http.server -d dist 8000

Content lives in content/site.json; static files (CSS, demo reports) in site/.
"""

from __future__ import annotations

import html
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"


def e(text: str) -> str:
    return html.escape(str(text), quote=True)


def is_external(url: str) -> bool:
    return url.startswith(("http://", "https://", "mailto:"))


def href(url: str, depth: int) -> str:
    """Relative links work from the root and from /projects/."""
    if not url or is_external(url) or url.startswith("#"):
        return url
    return "../" * depth + url


def page(title: str, description: str, body: str, data: dict, depth: int = 0, canonical: str = "", up: str | None = None) -> str:
    up = "../" * depth if up is None else up
    contact = data["contact"]
    canon = f'<link rel="canonical" href="{e(data["site_url"].rstrip("/") + "/" + canonical)}">' if data.get("site_url") else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta name="color-scheme" content="light dark">
{canon}
<link rel="stylesheet" href="{up}assets/style.css">
<link rel="icon" href="{up}assets/favicon.svg" type="image/svg+xml">
</head>
<body>
<header class="top"><div class="wrap">
  <a class="brand" href="{up}index.html">{e(data["name"])}</a>
  <nav class="links" aria-label="Main">
    <a href="{up}index.html#services">Services</a>
    <a href="{up}index.html#work">Work</a>
    <a class="opt" href="{up}index.html#free-scan">Free tools</a>
    <a href="{up}index.html#contact">Contact</a>
  </nav>
</div></header>
<main>
{body}
</main>
<footer><div class="wrap">
  <span>© {date.today().year} {e(data["name"])} · Demo projects use synthetic or demo data and say so.</span>
  <span><a href="{e(contact["github"])}">GitHub</a>{f' · <a href="{e(contact["linkedin"])}">LinkedIn</a>' if contact.get("linkedin") else ""}</span>
</div></footer>
</body>
</html>
"""


def service_card(s: dict, projects: dict) -> str:
    proof = projects.get(s["proof"])
    proof_link = f'<a href="projects/{e(proof["slug"])}.html">Proof: {e(proof["name"])}</a>' if proof else ""
    if s.get("case_study"):
        proof_link = f'<a href="case-studies/{e(s["id"].lower())}.html">Case study →</a> ' + proof_link
    guarantee = f'<p class="guarantee">{e(s["guarantee"])}</p>' if s.get("guarantee") else ""
    items = "".join(f"<li>{e(d)}</li>" for d in s["deliverables"])
    return f"""<article class="card" id="{e(s["id"].lower())}">
  <h3><span class="sid">{e(s["id"])}</span>{e(s["name"])}</h3>
  <p class="muted">{e(s["problem"])}</p>
  <ul>{items}</ul>
  <div class="price">
    <div><b>Founding</b><span>{e(s["founding"])}</span></div>
    <div><b>Standard</b><span>{e(s["standard"])}</span></div>
    <div><b>India</b><span>{e(s["india"])}</span></div>
  </div>
  {guarantee}
  <p class="muted">{e(s["days"])} · {e(s["access"])}</p>
  <div class="foot">{proof_link}</div>
</article>"""


def project_links(p: dict, depth: int) -> str:
    links = [f'<a href="{e(p["repo"])}">Code on GitHub</a>']
    if p.get("demo"):
        links.append(f'<a href="{e(href(p["demo"], depth))}">{e(p["demo_label"] or "Demo")}</a>')
    if p.get("video"):
        links.append(f'<a href="{e(p["video"])}">Demo video</a>')
    return " · ".join(links)


def extra_demos(p: dict, depth: int) -> str:
    """More sample reports for a project (e.g. the security check's before, retest and DPDP views)."""
    # A local report that has not been generated yet (e.g. the real sandbox scan) is simply not linked.
    items = [d for d in (p.get("extra_demos") or []) if is_external(d["url"]) or (ROOT / "site" / d["url"]).exists()]
    if not items:
        return ""
    links = " · ".join(f'<a href="{e(href(d["url"], depth))}">{e(d["label"])}</a>' for d in items)
    return f'<p class="muted">More sample reports: {links}</p>'


def project_card(p: dict) -> str:
    tags = "".join(f"<li>{e(t)}</li>" for t in p["stack"])
    cls = "card flagship" if p["kind"].startswith("Flagship") else "card"
    return f"""<article class="{cls}">
  <div>
    <div class="kind">{e(p["kind"])}</div>
    <h3>{e(p["name"])}</h3>
    <span class="label {e(p["label_class"])}">{e(p["label"])}</span>
    <p>{e(p["summary"])}</p>
  </div>
  <div><ul class="tags">{tags}</ul></div>
  <div class="foot"><a href="projects/{e(p["slug"])}.html">Case study →</a> {project_links(p, 0)}</div>
</article>"""


def index(data: dict) -> str:
    projects = {p["slug"]: p for p in data["projects"]}
    services = "\n".join(service_card(s, projects) for s in data["services"])
    work = "\n".join(project_card(p) for p in data["projects"])
    about = "".join(f"<p>{e(x)}</p>" for x in data["about"])
    c = data["contact"]
    contact_links = [f'<a class="btn primary" href="mailto:{e(c["email"])}">Email {e(c["email"])}</a>']
    if c.get("calendar"):
        contact_links.append(f'<a class="btn" href="{e(c["calendar"])}">Book a 15-minute call</a>')
    contact_links.append(f'<a class="btn" href="{e(c["github"])}">GitHub</a>')
    if c.get("linkedin"):
        contact_links.append(f'<a class="btn" href="{e(c["linkedin"])}">LinkedIn</a>')
    body = f"""
<div class="wrap hero">
  <p class="eyebrow">{e(data["role"])}</p>
  <h1>Cheaper cloud. Safer pipelines. Shorter outages.</h1>
  <p class="lead">{e(data["tagline"])}</p>
  <div class="actions">
    <a class="btn primary" href="#free-scan">Get a free ops health scan</a>
    <a class="btn" href="tools/bedrock-calculator/">Try the Bedrock bill calculator</a>
    <a class="btn" href="#services">See services and prices</a>
  </div>
  <p class="meta-line">{e(data["location"])}</p>
</div>

<section id="services"><div class="wrap">
  <h2>Services</h2>
  <p class="sub">Fixed scope, fixed price, a written deliverable at the end. Founding prices apply to my first clients in exchange for an honest review.</p>
  <div class="grid">{services}</div>
</div></section>

<section id="work"><div class="wrap">
  <h2>Work</h2>
  <p class="sub">Every project is open source and labelled honestly: what runs live, what runs on demand to save cost, and which data is synthetic.</p>
  <div class="grid">{work}</div>
</div></section>

<section id="free-scan"><div class="wrap">
  <h2>Free tools</h2>
  <p class="sub">Useful on their own, with or without hiring me.</p>
  <div class="grid">
  <div class="callout">
    <h3>Bedrock Bill-Shock Calculator</h3>
    <p>Building on Amazon Bedrock? The pricing page multiplies tokens by question and answer. Your bill also pays for the system prompt, the chat history, retrieved documents, agent loops, Guardrails and the vector store - on every call. See the real number and the changes that cut it most. Runs in your browser; nothing is sent anywhere.</p>
    <div class="actions"><a class="btn primary" href="tools/bedrock-calculator/">Open the calculator</a></div>
  </div>
  <div class="callout">
    <h3>Free ops health scan with Lifeline</h3>
    <p>Send me your GitHub organisation and domain. I run <a href="projects/lifeline.html">Lifeline</a> - my open-source resilience scorecard - and send you a short report: domain and TLS expiry, who holds the keys, CI pipeline risks, backup independence and cloud-credit runway. Each finding maps to one of the services above, so you know what to fix first - with or without me.</p>
    <div class="actions"><a class="btn primary" href="mailto:{e(c["email"])}?subject=Free%20Lifeline%20scan">Ask for a free scan</a></div>
  </div>
  </div>
</div></section>

<section id="how"><div class="wrap">
  <h2>How I work</h2>
  <div class="steps">
    <div><h3>15-minute call</h3><p>We agree on the problem, the scope and a fixed price. No production access needed to start.</p></div>
    <div><h3>Least-privilege access</h3><p>Read-only roles or a pull request - never shared passwords or long-lived keys. You can revoke access any time.</p></div>
    <div><h3>Evidence, not opinions</h3><p>Every engagement ends with a report, a pull request or a runbook you keep, plus a short handover video.</p></div>
    <div><h3>30-day follow-up</h3><p>I check the fixes held and the numbers moved, and answer questions for a month.</p></div>
  </div>
</div></section>

<section id="about"><div class="wrap">
  <h2>About</h2>
  {about}
</div></section>

<section id="contact"><div class="wrap">
  <h2>Contact</h2>
  <p class="sub">Tell me what hurts - the bill, the pipeline or the pager. I reply within one working day (IST).</p>
  <div class="actions">{"".join(contact_links)}</div>
</div></section>
"""
    return page(f'{data["name"]} - {data["role"]}', data["tagline"], body, data, 0, "")


def case_study(p: dict, data: dict) -> str:
    services = {s["id"]: s for s in data["services"]}
    highlights = "".join(f"<li>{e(h)}</li>" for h in p["highlights"])
    tags = "".join(f"<li>{e(t)}</li>" for t in p["stack"])
    linked = "".join(
        f'<li><a href="../{service_url(services[sid])}">{e(sid)} {e(services[sid]["name"])}</a></li>'
        for sid in p.get("services", []) if sid in services)
    body = f"""
<div class="wrap case">
  <p class="back"><a href="../index.html#work">← All work</a></p>
  <div class="kind">{e(p["kind"])}</div>
  <h1>{e(p["name"])}</h1>
  <span class="label {e(p["label_class"])}">{e(p["label"])}</span>
  <p class="lead">{e(p["summary"])}</p>
  <p>{project_links(p, 1)}</p>
  {extra_demos(p, 1)}
  <h2>Highlights</h2>
  <ul>{highlights}</ul>
  <h2>Stack</h2>
  <ul class="tags">{tags}</ul>
  <h2>Services it proves</h2>
  <ul>{linked}</ul>
  <h2>More detail</h2>
  <p>The README in the repository has the architecture diagram, the exact commands, the costs and the design trade-offs.</p>
</div>
"""
    return page(f'{p["name"]} - {data["name"]}', p["summary"], body, data, 1, f'projects/{p["slug"]}.html')


def service_url(s: dict) -> str:
    """Where a service is explained best: its case study page, else its card on the home page."""
    return f'case-studies/{s["id"].lower()}.html' if s.get("case_study") else f'index.html#{s["id"].lower()}'


def flow_diagram(steps: list[str]) -> str:
    """The engagement as a row of numbered boxes with arrows (a column on phones). Pure HTML/CSS:
    readable without images, follows the light/dark theme, and screen readers get an ordered list."""
    items = "".join(f'<li><span class="n">{i}</span>{e(step)}</li>' for i, step in enumerate(steps, 1))
    return f'<ol class="flow" aria-label="How the engagement works, step by step">{items}</ol>'


def case_study_page(s: dict, data: dict) -> str:
    c = s["case_study"]
    projects = {p["slug"]: p for p in data["projects"]}
    proof = projects.get(s["proof"])

    def bullets(items: list[str]) -> str:
        return "".join(f"<li>{e(x)}</li>" for x in items)

    plan = "".join(f'<li><b>{e(x["when"])}</b><span>{e(x["what"])}</span></li>' for x in c["plan"])
    proof_links = ""
    if proof:
        proof_links = f'<p><a href="../projects/{e(proof["slug"])}.html">The demo project: {e(proof["name"])}</a> · {project_links(proof, 1)}</p>'
    guarantee = f'<p class="guarantee">{e(s["guarantee"])}</p>' if s.get("guarantee") else ""
    email = data["contact"]["email"]
    body = f"""
<div class="wrap case">
  <p class="back"><a href="../index.html#services">← All services</a></p>
  <div class="kind">Case study · {e(s["id"])} {e(s["name"])}</div>
  <h1>{e(c["title"])}</h1>
  <p class="lead">{e(c["summary"])}</p>
  <p class="note">This case study uses my own demo project and synthetic data. It shows exactly how the
  engagement works and what you receive; it is not a story about a client.</p>

  <h2>The typical situation</h2>
  <p>{e(c["situation"])}</p>
  <div class="two">
    <div><h2>The problem</h2><ul>{bullets(c["problem"])}</ul></div>
    <div><h2>The solution</h2><ul>{bullets(c["solution"])}</ul></div>
  </div>

  <h2>How it works</h2>
  {flow_diagram(c["flow"])}

  <h2>What I'll do</h2>
  <ol class="plan">{plan}</ol>

  <h2>Evidence from the demo</h2>
  <ul>{bullets(c["evidence"])}</ul>
  {proof_links}

  <div class="two">
    <div><h2>What you keep</h2><ul>{bullets(c["keep"])}</ul></div>
    <div><h2>Not included</h2><ul>{bullets(c["not_included"])}</ul></div>
  </div>

  <h2>Price and access</h2>
  <div class="price">
    <div><b>Founding</b><span>{e(s["founding"])}</span></div>
    <div><b>Standard</b><span>{e(s["standard"])}</span></div>
    <div><b>India</b><span>{e(s["india"])}</span></div>
  </div>
  {guarantee}
  <p class="muted">{e(s["days"])} · {e(s["access"])}</p>
  <div class="actions">
    <a class="btn primary" href="{e("mailto:" + email + "?subject=" + quote(s["id"] + " - " + s["name"]))}">Ask about {e(s["id"])}</a>
    <a class="btn" href="../index.html#services">See all services</a>
  </div>
</div>
"""
    return page(f'{c["title"]} - {s["id"]} case study - {data["name"]}', c["summary"], body, data, 1, f'case-studies/{s["id"].lower()}.html')


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#0f6b5c"/><path d="M8 17l5 5 11-12" stroke="#fff" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>"""


def build() -> None:
    data = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
    if os.environ.get("SITE_URL"):  # set by scripts/up.sh after Terraform knows the URL
        data["site_url"] = os.environ["SITE_URL"]
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "site", DIST)
    (DIST / "assets" / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    (DIST / "index.html").write_text(index(data), encoding="utf-8")
    (DIST / "projects").mkdir(exist_ok=True)
    for p in data["projects"]:
        (DIST / "projects" / f'{p["slug"]}.html').write_text(case_study(p, data), encoding="utf-8")
    (DIST / "case-studies").mkdir(exist_ok=True)
    for s in data["services"]:
        if s.get("case_study"):
            (DIST / "case-studies" / f'{s["id"].lower()}.html').write_text(case_study_page(s, data), encoding="utf-8")
    # Served by CloudFront for any missing path, so it uses absolute links.
    (DIST / "404.html").write_text(page("Not found", "Page not found", '<div class="wrap case"><h1>Page not found</h1><p><a href="/index.html">Back to the start</a></p></div>', data, up="/"), encoding="utf-8")
    (DIST / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    if data.get("site_url"):
        base = data["site_url"].rstrip("/")
        urls = [f"{base}/"] + [f'{base}/projects/{p["slug"]}.html' for p in data["projects"]]
        urls += [f'{base}/case-studies/{s["id"].lower()}.html' for s in data["services"] if s.get("case_study")]
        (DIST / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{e(u)}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    if data["contact"]["email"] == "you@example.com":
        print("note: set contact.email in content/site.json before publishing", file=sys.stderr)
    n_cs = sum(1 for s in data["services"] if s.get("case_study"))
    print(f"built {DIST} ({len(data['projects'])} project pages, {n_cs} service case studies)")


if __name__ == "__main__":
    build()
