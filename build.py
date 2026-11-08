"""Build the static portfolio site into dist/ (Python standard library only).

    python3 build.py            # -> dist/
    python3 -m http.server -d dist 8000

Content lives in content/site.json; static files (CSS, JS, fonts, photo, demo reports) in site/.
Pages: home, services (+ one page per service), work (+ one page per project), open source,
about, resume, contact (Web3Forms contact and free-scan forms), thanks, 404.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
WEB3FORMS = "https://api.web3forms.com/submit"

NAV = [("services.html", "Services"), ("work.html", "Work"), ("open-source.html", "Open source"),
       ("about.html", "About"), ("resume.html", "Resume")]

ARROW = '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h11m-4-4 4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
EXT = '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"><path d="M8 5H5v10h10v-3M11 4h5v5M16 4l-7 7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>'
FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#0f766e"/><text x="16" y="21.5" font-family="Arial,Helvetica,sans-serif" font-size="14" font-weight="700" text-anchor="middle" fill="#fff">OA</text></svg>"""


def e(text) -> str:
    return html.escape(str(text), quote=True)


def is_external(url: str) -> bool:
    return url.startswith(("http://", "https://", "mailto:"))


def href(url: str, depth: int) -> str:
    """Relative links work from the root and from /projects/ or /case-studies/."""
    if not url or is_external(url) or url.startswith("#"):
        return url
    return "../" * depth + url


def version(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10] if path.exists() else "0"


def from_price(text: str) -> str:
    """'$99-199' -> '$99' (the lowest price of a range)."""
    return text.split("-")[0].strip()


def picture(data: dict, depth: int, cls: str, sizes: str, eager: bool = False) -> str:
    ph = data["photo"]
    sq, sm = href(ph["square"], depth), href(ph["small"], depth)
    load = 'fetchpriority="high"' if eager else 'loading="lazy"'
    return (f'<picture class="{cls}"><source type="image/webp" srcset="{sm}.webp 320w, {sq}.webp 640w" sizes="{sizes}">'
            f'<img src="{sq}.jpg" srcset="{sm}.jpg 320w, {sq}.jpg 640w" sizes="{sizes}" width="640" height="640" '
            f'alt="{e(ph["alt"])}" {load} decoding="async"></picture>')


def book_url(data: dict, depth: int) -> str:
    c = data["contact"]
    return c["calendar"] or href("contact.html", depth)


def person_ld(data: dict) -> dict:
    c = data["contact"]
    same = [c["github"]] + ([c["linkedin"]] if c.get("linkedin") else [])
    ld = {"@context": "https://schema.org", "@type": "Person", "name": data["name"], "jobTitle": data["role"],
          "address": {"@type": "PostalAddress", "addressLocality": "Indore", "addressCountry": "IN"},
          "email": "mailto:" + c["email"], "sameAs": same,
          "knowsAbout": ["AWS", "Terraform", "GitHub Actions", "Kubernetes", "DevSecOps", "FinOps", "Ansible"]}
    if data.get("site_url"):
        ld["url"] = data["site_url"].rstrip("/") + "/"
        ld["image"] = data["site_url"].rstrip("/") + "/" + data["photo"]["square"] + ".jpg"
    return ld


def page(title: str, description: str, body: str, data: dict, depth: int = 0, path: str = "",
         active: str = "", ld: dict | list | None = None, up: str | None = None) -> str:
    up = "../" * depth if up is None else up
    c = data["contact"]
    site = data.get("site_url", "").rstrip("/")
    canon = f'<link rel="canonical" href="{e(site + "/" + path)}">\n<meta property="og:url" content="{e(site + "/" + path)}">' if site else ""
    og_img = f'<meta property="og:image" content="{e(site)}/assets/og.jpg">\n<meta name="twitter:image" content="{e(site)}/assets/og.jpg">' if site else ""
    ld_html = ""
    if ld:
        ld_html = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    current = ' aria-current="page"'
    nav = "".join(f'<a href="{up}{u}"{current if active == u else ""}>{e(t)}</a>' for u, t in NAV)
    css_v, js_v = version(ROOT / "site/assets/style.css"), version(ROOT / "site/assets/site.js")
    year = datetime.now(timezone.utc).year
    linkedin = f'<a href="{e(c["linkedin"])}">LinkedIn</a>' if c.get("linkedin") else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta name="author" content="{e(data["name"])}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(data["name"])}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta name="twitter:card" content="summary_large_image">
{og_img}
{canon}
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#0f766e">
<link rel="preload" href="{up}assets/fonts/inter-latin-wght.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{up}assets/style.css?v={css_v}">
<link rel="icon" href="{up}assets/favicon.svg" type="image/svg+xml">
{ld_html}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap bar">
  <a class="brand" href="{up}index.html"><span class="mark" aria-hidden="true">OA</span><span>{e(data["name"])}</span></a>
  <nav class="links" aria-label="Main">{nav}</nav>
  <a class="btn primary small hire" href="{up}contact.html">Hire me</a>
  <details class="menu"><summary aria-label="Menu">Menu</summary><nav aria-label="Mobile">{nav}<a href="{up}contact.html">Contact</a></nav></details>
</div></header>
<main id="main">
{body}
</main>
<footer class="foot"><div class="wrap fgrid">
  <div>
    <p class="fbrand">{e(data["name"])}</p>
    <p class="muted">{e(data["role"])} · {e(data["location"])}</p>
    <p><a href="mailto:{e(c["email"])}">{e(c["email"])}</a></p>
  </div>
  <nav class="flinks" aria-label="Footer">
    <a href="{up}services.html">Services</a><a href="{up}work.html">Work</a><a href="{up}index.html#free-tools">Free tools</a>
    <a href="{up}open-source.html">Open source</a><a href="{up}about.html">About</a><a href="{up}resume.html">Resume</a>
    <a href="{up}contact.html">Contact</a><a href="{e(c["github"])}">GitHub</a>{linkedin}
  </nav>
  <p class="small muted fnote">© {year} {e(data["name"])}. No cookies or tracking on this site. Demo projects use synthetic or
  demo data and say so; real client results appear only with written permission.</p>
</div></footer>
<script src="{up}assets/site.js?v={js_v}" defer></script>
</body>
</html>
"""


# ---------- building blocks ----------

def section(sid: str, eyebrow: str, title: str, sub: str, inner: str, cls: str = "") -> str:
    sub_html = f'<p class="sub">{e(sub)}</p>' if sub else ""
    return f"""<section id="{sid}" class="sec {cls}"><div class="wrap">
  <div class="head"><p class="eyebrow">{e(eyebrow)}</p><h2>{e(title)}</h2>{sub_html}</div>
  {inner}
</div></section>"""


def service_url(s: dict) -> str:
    return f'case-studies/{s["id"].lower()}.html'


def service_card(s: dict, depth: int) -> str:
    items = "".join(f"<li>{e(h)}</li>" for h in s.get("highlights", s["deliverables"][:3]))
    return f"""<article class="card svc">
  <div class="row"><span class="pill">{e(s["id"])}</span><span class="muted small">{e(s["days"])}</span></div>
  <h3><a class="stretch" href="{href(service_url(s), depth)}">{e(s["name"])}</a></h3>
  <p>{e(s["short"])}</p>
  <ul class="checks">{items}</ul>
  <div class="price-row"><span><b>From {e(from_price(s["founding"]))}</b> <span class="muted">· India from {e(from_price(s["india"]))}</span></span>
  <span class="go">Details {ARROW}</span></div>
</article>"""


def service_row(s: dict, depth: int) -> str:
    return f"""<a class="srow" href="{href(service_url(s), depth)}">
  <span class="pill">{e(s["id"])}</span>
  <span class="srow-main"><b>{e(s["name"])}</b><span class="muted">{e(s["short"])}</span></span>
  <span class="srow-price">from {e(from_price(s["founding"]))} {ARROW}</span>
</a>"""


def status_pill(p: dict) -> str:
    return f'<span class="status {e(p["label_class"])}">{e(p["label"])}</span>'


def project_card(p: dict, depth: int) -> str:
    tags = "".join(f"<li>{e(t)}</li>" for t in p["stack"][:4])
    demo = ""
    if p.get("demo"):
        demo = f'<a class="ext" href="{e(href(p["demo"], depth))}">{e(p.get("demo_label") or "Demo")} {EXT}</a>'
    return f"""<article class="card work">
  <div class="row">{status_pill(p)}</div>
  <h3><a href="{href("projects/" + p["slug"] + ".html", depth)}">{e(p["name"])}</a></h3>
  <p>{e(p["short"])}</p>
  <ul class="tags">{tags}</ul>
  <div class="links-row"><a href="{href("projects/" + p["slug"] + ".html", depth)}">Case study {ARROW}</a>{demo}</div>
</article>"""


def project_links(p: dict, depth: int) -> str:
    links = [f'<a class="btn" href="{e(p["repo"])}">Code on GitHub {EXT}</a>']
    if p.get("demo"):
        links.insert(0, f'<a class="btn primary" href="{e(href(p["demo"], depth))}">{e(p.get("demo_label") or "Demo")}</a>')
    if p.get("video"):
        links.append(f'<a class="btn" href="{e(p["video"])}">Demo video {EXT}</a>')
    return "".join(links)


def extra_demos(p: dict, depth: int) -> str:
    """More sample reports (a local report that has not been generated yet is simply not linked)."""
    items = [d for d in (p.get("extra_demos") or []) if is_external(d["url"]) or (ROOT / "site" / d["url"]).exists()]
    if not items:
        return ""
    lis = "".join(f'<li><a href="{e(href(d["url"], depth))}">{e(d["label"])}</a></li>' for d in items)
    return f'<h2>More sample reports</h2><ul class="plain">{lis}</ul>'


def steps_html() -> str:
    steps = [("15-minute call", "We agree on the problem, the scope and a fixed price. No access needed to start."),
             ("Least-privilege access", "A read-only role or a pull request. Never passwords or long-lived keys."),
             ("Evidence you keep", "A report, a pull request or a runbook, and a short handover video."),
             ("30-day follow-up", "I check that the fixes held and answer questions for a month.")]
    return '<ol class="steps">' + "".join(f"<li><b>{e(t)}</b><span>{e(x)}</span></li>" for t, x in steps) + "</ol>"


def cta_band(data: dict, depth: int) -> str:
    c = data["contact"]
    book = book_url(data, depth)
    label = "Book a 15-minute call" if c.get("calendar") else "Start a conversation"
    return f"""<section class="cta"><div class="wrap cta-in">
  <div><h2>Have a cloud bill, pipeline or outage that worries you?</h2>
  <p>Tell me in a few lines. {e(c["response"])}</p></div>
  <div class="actions"><a class="btn light" href="{e(book)}">{label}</a>
  <a class="btn ghost-light" href="mailto:{e(c["email"])}">{e(c["email"])}</a></div>
</div></section>"""


def faq_html(items: list[dict]) -> str:
    return '<div class="faq">' + "".join(
        f"<details><summary>{e(f['q'])}</summary><p>{e(f['a'])}</p></details>" for f in items) + "</div>"


def gh(repo: str, number: int) -> str:
    return f"https://github.com/{repo}/pull/{number}"


# ---------- pages ----------

def index(data: dict) -> str:
    svcs = {s["id"]: s for s in data["services"]}
    projs = {p["slug"]: p for p in data["projects"]}
    c = data["contact"]
    featured = "".join(service_card(svcs[i], 0) for i in data["featured"])
    others = "".join(service_row(s, 0) for s in data["services"] if s["id"] not in data["featured"])
    work = "".join(project_card(projs[x], 0) for x in data["selected_work"])
    proof = "".join(f'<div><b>{e(p["value"])}</b><span>{e(p["label"])}</span></div>' for p in data["proof_bar"])
    os_ = data["open_source"]
    counts: dict[str, int] = {"kyverno": 0, "pipecd": 0, "meshery": 0}
    for pr in os_["merged"]:
        org = pr["repo"].split("/")[1]
        counts[org] = counts.get(org, 0) + 1
    org_names = {"kyverno": "Kyverno", "pipecd": "PipeCD", "meshery": "Meshery"}
    os_rows = "".join(f'<li><b>{e(org_names.get(k, k))}</b><span>{v} merged</span></li>' for k, v in counts.items() if v)
    book = book_url(data, 0)
    book_label = "Book a 15-minute call" if c.get("calendar") else "Hire me"
    calc = next((p for p in data["projects"] if p["slug"] == "bedrock-cost-calculator"), None)
    body = f"""
<section class="hero"><div class="wrap hero-in">
  <div class="hero-text">
    <p class="avail"><span class="dot" aria-hidden="true"></span>{e(data["availability"])}</p>
    <h1>{e(data["name"])}</h1>
    <p class="role">{e(data["role"])}</p>
    <p class="headline">{e(data["headline"])}</p>
    <p class="lead">{e(data["tagline"])}</p>
    <div class="actions">
      <a class="btn primary" href="{e(book)}">{book_label}</a>
      <a class="btn" href="services.html">Services and prices</a>
    </div>
    <p class="hint">Hiring for a role? <a href="resume.html">View my résumé {ARROW}</a></p>
  </div>
  <div class="hero-photo">{picture(data, 0, "avatar", "(max-width: 760px) 240px, 340px", eager=True)}
    <p class="photo-note">{e(data["location"])}</p>
  </div>
</div>
<div class="wrap"><div class="proof">{proof}</div></div>
</section>

{section("services", "Services", "Fixed scope. Fixed price. A deliverable you keep.",
         "Founding prices for my first clients, in exchange for an honest review.",
         f'<div class="grid two">{featured}</div><h3 class="also">Also available</h3><div class="rows">{others}</div>'
         f'<p class="more"><a href="services.html">Compare all services {ARROW}</a></p>')}

{section("work", "Selected work", "Built in the open, labelled honestly",
         "Every project says what runs live, what runs on demand to save cost, and which data is synthetic.",
         f'<div class="grid two">{work}</div><p class="more"><a href="work.html">All 9 projects {ARROW}</a></p>', "alt")}

<section class="sec dark"><div class="wrap os">
  <div><p class="eyebrow">Open source</p><h2>Contributor to CNCF projects, maintainer of my own</h2>
  <p>{e(os_.get("home_intro", os_["intro"]))}</p>
  <div class="actions"><a class="btn light" href="open-source.html">See every pull request</a></div></div>
  <ul class="os-list">{os_rows}<li><b>Lifeline</b><span>creator and maintainer</span></li></ul>
</div></section>

{section("how", "How I work", "Low risk for you, from the first call", "", steps_html())}

{section("free-tools", "Free tools", "Useful with or without hiring me", "",
         f'''<div class="grid two">
  <article class="card"><h3><a href="tools/bedrock-calculator/">Bedrock Bill-Shock Calculator</a></h3>
  <p>{e(calc["short"] if calc else "")} Runs in your browser; nothing is sent anywhere.</p>
  <div class="links-row"><a href="tools/bedrock-calculator/">Open the calculator {ARROW}</a></div></article>
  <article class="card"><h3><a href="contact.html#free-scan">Free ops health scan</a></h3>
  <p>Send me your GitHub organisation and domain. I run Lifeline, my open-source scorecard, and send you a short report
  of the risks worth fixing first - with or without me.</p>
  <div class="links-row"><a href="contact.html#free-scan">Request a free scan {ARROW}</a></div></article>
</div>''', "alt")}

<section class="sec"><div class="wrap about-mini">
  {picture(data, 0, "avatar sm", "120px")}
  <div><p class="eyebrow">About</p><p class="big">{e(data["about"][0])}</p>
  <div class="links-row"><a href="about.html">More about me {ARROW}</a><a href="resume.html">Résumé {ARROW}</a></div></div>
</div></section>

{cta_band(data, 0)}
"""
    return page(f'{data["name"]} - {data["role"]}', data["tagline"], body, data, 0, "", "", person_ld(data))


def services_page(data: dict) -> str:
    svcs = {s["id"]: s for s in data["services"]}
    featured = "".join(service_card(svcs[i], 0) for i in data["featured"])
    others = "".join(service_card(s, 0) for s in data["services"] if s["id"] not in data["featured"])
    rows = "".join(
        f'<tr><td><a href="{service_url(s)}">{e(s["id"])} {e(s["name"])}</a></td><td>{e(s["days"])}</td>'
        f'<td>{e(s["founding"])}</td><td>{e(s["standard"])}</td><td>{e(s["india"])}</td></tr>' for s in data["services"])
    ld = {"@context": "https://schema.org", "@type": "ProfessionalService", "name": data["name"] + " - cloud and DevOps services",
          "areaServed": "Worldwide", "provider": person_ld(data),
          "hasOfferCatalog": {"@type": "OfferCatalog", "name": "Services", "itemListElement": [
              {"@type": "Offer", "itemOffered": {"@type": "Service", "name": s["name"]}, "priceCurrency": "USD",
               "price": from_price(s["founding"]).lstrip("$").replace(",", "")} for s in data["services"]]}}
    body = f"""
<section class="page-head"><div class="wrap">
  <p class="eyebrow">Services</p><h1>Small, fixed-price packages</h1>
  <p class="lead">Each one ends with something you keep: a report, a pull request or a runbook. Prices start low for my first
  clients (founding price) in exchange for an honest review.</p>
</div></section>
{section("featured", "Most requested", "Start here", "", f'<div class="grid two">{featured}</div>')}
{section("more", "Also available", "When you need more than an audit", "", f'<div class="grid two">{others}</div>', "alt")}
{section("prices", "Prices", "All services at a glance", "Founding prices are for my first three clients per service. India prices are in rupees.",
         f'<div class="table-wrap"><table class="prices"><thead><tr><th>Service</th><th>Time</th><th>Founding</th><th>Standard</th><th>India</th></tr></thead><tbody>{rows}</tbody></table></div>')}
{section("how", "How I work", "Low risk for you, from the first call", "", steps_html(), "alt")}
{section("faq", "Questions", "Before you ask", "", faq_html(data["faq"]))}
{cta_band(data, 0)}
"""
    return page(f'Services and prices - {data["name"]}', "Fixed-price cloud, CI/CD and security packages for small teams on AWS and GitHub.",
                body, data, 0, "services.html", "services.html", ld)


def service_page(s: dict, data: dict) -> str:
    c = s["case_study"]
    projects = {p["slug"]: p for p in data["projects"]}
    proof = projects.get(s["proof"])

    def bullets(items: list[str]) -> str:
        return "".join(f"<li>{e(x)}</li>" for x in items)

    plan = "".join(f'<li><b>{e(x["when"])}</b><span>{e(x["what"])}</span></li>' for x in c["plan"])
    flow = "".join(f'<li><span class="n">{i}</span>{e(step)}</li>' for i, step in enumerate(c["flow"], 1))
    guarantee = f'<p class="guarantee">{e(s["guarantee"])}</p>' if s.get("guarantee") else ""
    proof_html = ""
    if proof:
        proof_html = f'<p class="proof-link">Demo project: <a href="../projects/{e(proof["slug"])}.html">{e(proof["name"])}</a></p>'
    email = data["contact"]["email"]
    mailto = "mailto:" + email + "?subject=" + quote(s["id"] + " - " + s["name"])
    book = book_url(data, 1)
    body = f"""
<section class="page-head"><div class="wrap">
  <p class="back"><a href="../services.html">← All services</a></p>
  <p class="eyebrow">{e(s["id"])} · {e(s["days"])}</p>
  <h1>{e(s["name"])}</h1>
  <p class="lead">{e(s["short"])}</p>
</div></section>
<div class="wrap svc-layout">
  <article class="prose">
    <h2>Who it is for</h2>
    <p>{e(c["situation"])}</p>
    <h2>The problem</h2><ul>{bullets(c["problem"])}</ul>
    <h2>What I do</h2><ul>{bullets(c["solution"])}</ul>
    <h2>How it works</h2><ol class="flow">{flow}</ol>
    <h2>Day by day</h2><ol class="plan">{plan}</ol>
    <h2>Evidence from the demo</h2>
    <p class="note">The evidence below comes from my own demo project with synthetic data. It shows exactly what you
    receive; it is not a story about a client.</p>
    <ul>{bullets(c["evidence"])}</ul>{proof_html}
    <div class="two"><div><h2>What you keep</h2><ul>{bullets(c["keep"])}</ul></div>
    <div><h2>Not included</h2><ul>{bullets(c["not_included"])}</ul></div></div>
    <h2>Questions</h2>{faq_html(data["faq"])}
  </article>
  <aside class="side"><div class="card sticky">
    <p class="eyebrow">Price</p>
    <dl class="pricelist"><dt>Founding</dt><dd>{e(s["founding"])}</dd><dt>Standard</dt><dd>{e(s["standard"])}</dd><dt>India</dt><dd>{e(s["india"])}</dd></dl>
    {guarantee}
    <p class="small muted"><b>Time:</b> {e(s["days"])}<br><b>Access:</b> {e(s["access"])}</p>
    <a class="btn primary block" href="{e(book)}">{"Book a 15-minute call" if data["contact"].get("calendar") else "Ask about " + e(s["id"])}</a>
    <a class="btn block" href="{e(mailto)}">Email me about it</a>
  </div></aside>
</div>
{cta_band(data, 1)}
"""
    return page(f'{s["name"]} - {data["name"]}', s["short"], body, data, 1, service_url(s), "services.html")


GROUPS = [("Flagship and free tools", ("Flagship", "Free tool")), ("Service kits", ("Freelance demo",)),
          ("Platform projects", ("Resume project",))]


def work_page(data: dict) -> str:
    blocks = []
    for i, (title, kinds) in enumerate(GROUPS):
        items = [p for p in data["projects"] if p["kind"].startswith(kinds)]
        if items:
            cards = "".join(project_card(p, 0) for p in items)
            blocks.append(section(f"g{i}", "Work", title, "", f'<div class="grid two">{cards}</div>', "alt" if i % 2 else ""))
    body = f"""
<section class="page-head"><div class="wrap">
  <p class="eyebrow">Work</p><h1>Projects</h1>
  <p class="lead">Every project is open source, runs for real and is labelled honestly: what is live, what runs on demand to
  save cost, and which data is synthetic.</p>
</div></section>
{"".join(blocks)}
{cta_band(data, 0)}
"""
    return page(f'Work - {data["name"]}', "Open-source cloud, DevOps and DevSecOps projects, each labelled live, on demand or demo.",
                body, data, 0, "work.html", "work.html")


def project_page(p: dict, data: dict) -> str:
    services = {s["id"]: s for s in data["services"]}
    highlights = "".join(f"<li>{e(h)}</li>" for h in p["highlights"])
    tags = "".join(f"<li>{e(t)}</li>" for t in p["stack"])
    linked = "".join(service_card(services[sid], 1) for sid in p.get("services", []) if sid in services)
    body = f"""
<section class="page-head"><div class="wrap">
  <p class="back"><a href="../work.html">← All work</a></p>
  <p class="eyebrow">{e(p["kind"])}</p>
  <h1>{e(p["name"])}</h1>
  <p>{status_pill(p)}</p>
  <p class="lead">{e(p["summary"])}</p>
  <div class="actions">{project_links(p, 1)}</div>
</div></section>
<div class="wrap prose narrow">
  <h2>Highlights</h2><ul>{highlights}</ul>
  <h2>Built with</h2><ul class="tags">{tags}</ul>
  {extra_demos(p, 1)}
  <h2>More detail</h2>
  <p>The README in the repository has the architecture diagram, the exact commands, the costs and the design trade-offs.</p>
</div>
{section("proves", "Services", "What this project proves", "", f'<div class="grid two">{linked}</div>', "alt") if linked else ""}
"""
    return page(f'{p["name"]} - {data["name"]}', p["short"], body, data, 1, f'projects/{p["slug"]}.html', "work.html")


def open_source_page(data: dict) -> str:
    os_ = data["open_source"]

    def rows(items: list[dict], merged: bool) -> str:
        return "".join(
            f'<li><a href="{gh(x["repo"], x["number"])}"><span class="repo">{e(x["repo"])} #{x["number"]}</span>'
            f'<span class="t">{e(x["title"])}</span></a><span class="date">{"merged" if merged else "opened"} {e(x["date"])}</span></li>'
            for x in sorted(items, key=lambda x: x["date"], reverse=True))

    lifeline = next((p for p in data["projects"] if p["slug"] == "lifeline"), None)
    body = f"""
<section class="page-head"><div class="wrap">
  <p class="eyebrow">Open source</p><h1>Pull requests and projects</h1>
  <p class="lead">{e(os_["intro"])}</p>
  <div class="proof slim"><div><b>{len(os_["merged"])}</b><span>merged pull requests</span></div>
  <div><b>{len(os_["open"])}</b><span>open pull requests</span></div><div><b>11</b><span>repositories of my own</span></div></div>
</div></section>
{section("merged", "Merged", "Merged pull requests", "Kyverno, PipeCD and Meshery are CNCF projects.", f'<ul class="prs">{rows(os_["merged"], True)}</ul>')}
{section("open", "In review", "Open pull requests", "", f'<ul class="prs">{rows(os_["open"], False)}</ul>', "alt")}
{section("maintainer", "Maintainer", "Lifeline", lifeline["short"] if lifeline else "",
         f'<div class="actions"><a class="btn primary" href="projects/lifeline.html">About Lifeline</a><a class="btn" href="{e(lifeline["repo"] if lifeline else "")}">Repository {EXT}</a></div>')}
<p class="wrap small muted">List updated {e(os_["updated"])}. Live list: <a href="https://github.com/pulls?q=author%3AObaidAbdullah16+is%3Apr">GitHub search {EXT}</a></p>
"""
    return page(f'Open source - {data["name"]}', "Merged and open pull requests in CNCF projects, and the open-source tools I maintain.",
                body, data, 0, "open-source.html", "open-source.html")


def about_page(data: dict) -> str:
    c = data["contact"]
    paras = "".join(f"<p>{e(x)}</p>" for x in data["about"])
    facts = [("Based in", data["location"]), ("Focus", "AWS, Terraform, CI/CD security, Kubernetes, observability, FinOps"),
             ("Education", "B.E. Computer Engineering, IET DAVV Indore (2023-2027)"), ("Availability", data["availability"]),
             ("Replies", c["response"])]
    dl = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in facts)
    ph = data["photo"]
    portrait = (f'<picture class="portrait"><source type="image/webp" srcset="assets/img/obaid-portrait-720.webp">'
                f'<img src="assets/img/obaid-portrait-720.jpg" width="720" height="900" alt="{e(ph["alt"])}" loading="lazy" decoding="async"></picture>')
    body = f"""
<section class="page-head"><div class="wrap about">
  {portrait}
  <div><p class="eyebrow">About</p><h1>Hi, I'm Obaid.</h1>
  <div class="prose">{paras}</div>
  <dl class="facts">{dl}</dl>
  <div class="actions"><a class="btn primary" href="contact.html">Work with me</a><a class="btn" href="resume.html">Résumé</a>
  <a class="btn" href="{e(c["github"])}">GitHub {EXT}</a>{f'<a class="btn" href="{e(c["linkedin"])}">LinkedIn {EXT}</a>' if c.get("linkedin") else ""}</div></div>
</div></section>
{cta_band(data, 0)}
"""
    return page(f'About - {data["name"]}', data["about"][0], body, data, 0, "about.html", "about.html", person_ld(data))


def resume_page(data: dict) -> str:
    r, c = data["resume"], data["contact"]
    site = (data.get("site_url") or "").replace("https://", "")
    skills = "".join(f"<li><b>{e(s['area'])}:</b> {e(s['items'])}</li>" for s in r["skills"])

    def entries(items: list[dict]) -> str:
        out = []
        for x in items:
            pts = "".join(f"<li>{e(t)}</li>" for t in x["points"])
            name = e(x["name"])
            if x.get("slug"):
                name = f'<a href="projects/{e(x["slug"])}.html">{name}</a>'
            out.append(f'<div class="entry"><h3>{name} <span class="muted">· {e(x["stack"])}</span></h3><ul>{pts}</ul></div>')
        return "".join(out)

    edu = "".join(f'<div class="entry"><h3>{e(x["school"])}</h3><p>{e(x["degree"])} · {e(x["years"])}</p></div>' for x in r["education"])
    other = "".join(f"<li>{e(x)}</li>" for x in r["other"])
    contact_line = " · ".join([e(data["location"].split(" · ")[0]), f'<a href="mailto:{e(c["email"])}">{e(c["email"])}</a>',
                               f'<a href="{e(c["github"])}">github.com/ObaidAbdullah16</a>'] +
                              ([f'<a href="{e(c["linkedin"])}">{e(c["linkedin"].replace("https://www.", "").rstrip("/"))}</a>'] if c.get("linkedin") else []) +
                              ([f'<a href="{e(data["site_url"])}">{e(site)}</a>'] if site else []))
    pdf = r["pdf"]
    dl = f'<a class="btn primary" href="{pdf}" download>Download PDF</a>' if (ROOT / "site" / pdf).exists() else ""
    body = f"""
<section class="page-head noprint"><div class="wrap">
  <p class="eyebrow">Résumé</p><h1>For recruiters</h1>
  <p class="lead">{e(r["availability"])}</p>
  <div class="actions">{dl}<a class="btn" href="contact.html">Contact me</a></div>
</div></section>
<div class="wrap resume">
  <header class="r-head"><h2 class="r-name">{e(data["name"])}</h2><p class="r-role">{e(data["role"])}</p><p class="r-contact">{contact_line}</p></header>
  <section><h2>Summary</h2><p>{e(r["summary"])}</p></section>
  <section><h2>Skills</h2><ul class="skills">{skills}</ul></section>
  <section><h2>Projects</h2>{entries(r["projects"])}</section>
  <section><h2>Open source</h2>{entries(r["open_source"])}</section>
  <section><h2>Education</h2>{edu}</section>
  <section><h2>Other</h2><ul>{other}</ul></section>
</div>
"""
    return page(f'Résumé - {data["name"]}', r["summary"], body, data, 0, "resume.html", "resume.html", person_ld(data))


def contact_page(data: dict) -> str:
    c = data["contact"]
    site = (data.get("site_url") or "").rstrip("/")
    key = c.get("web3forms_key", "")
    options = "".join(f'<option>{e(s["id"])} - {e(s["name"])}</option>' for s in data["services"])
    redirect = f'<input type="hidden" name="redirect" value="{e(site)}/thanks.html">' if site else ""
    hidden_common = (f'<input type="hidden" name="access_key" value="{e(key)}">'
                     f'<input type="hidden" name="from_name" value="{e(site.replace("https://", "") or "Portfolio website")}">{redirect}'
                     '<input type="checkbox" name="botcheck" class="hp" tabindex="-1" autocomplete="off" aria-hidden="true">')
    if key:
        contact_form = f"""<form class="form" action="{WEB3FORMS}" method="POST" data-web3forms>
  {hidden_common}<input type="hidden" name="subject" value="New enquiry from your website">
  <div class="f2"><label>Your name<input name="name" required autocomplete="name"></label>
  <label>Email<input type="email" name="email" required autocomplete="email"></label></div>
  <div class="f2"><label><span>Company or website <span class="opt">optional</span></span><input name="company" autocomplete="organization"></label>
  <label>What do you need?<select name="topic"><option>Not sure yet</option>{options}<option>Internship or job opportunity</option><option>Something else</option></select></label></div>
  <label><span>Budget <span class="opt">optional</span></span><select name="budget"><option>Not sure yet</option><option>Under $200 / ₹15k</option><option>$200-500</option><option>$500-1,000</option><option>Over $1,000</option></select></label>
  <label>What is going on?<textarea name="message" rows="6" required placeholder="Your stack (AWS, GitHub, ...), what worries you, and any deadline."></textarea></label>
  <p class="small muted">I use your details only to reply. Never send passwords or keys here.</p>
  <button class="btn primary" type="submit">Send message</button><p class="form-status" role="status" aria-live="polite"></p>
</form>"""
        scan_form = f"""<form class="form" action="{WEB3FORMS}" method="POST" data-web3forms>
  {hidden_common}<input type="hidden" name="subject" value="Free scan request from your website">
  <div class="f2"><label>Your name<input name="name" required autocomplete="name"></label>
  <label>Email<input type="email" name="email" required autocomplete="email"></label></div>
  <div class="f2"><label>GitHub organisation or repository<input name="github" required placeholder="github.com/your-org"></label>
  <label><span>Domain <span class="opt">optional</span></span><input name="domain" placeholder="example.com"></label></div>
  <label><span>Anything I should know? <span class="opt">optional</span></span><textarea name="message" rows="3"></textarea></label>
  <label class="check"><input type="checkbox" name="permission" value="yes" required> I own or manage these and agree to a scan of their public information.</label>
  <button class="btn primary" type="submit">Request free scan</button><p class="form-status" role="status" aria-live="polite"></p>
</form>"""
    else:
        contact_form = (f'<div class="card"><h3>Send me an email</h3><p>Tell me your stack, what worries you and any deadline.</p>'
                        f'<a class="btn primary" href="mailto:{e(c["email"])}?subject={quote("Project enquiry")}">Email {e(c["email"])}</a></div>')
        scan_form = (f'<div class="card"><p>Email me your GitHub organisation (and domain, if you like). I reply with the report within a few days.</p>'
                     f'<a class="btn primary" href="mailto:{e(c["email"])}?subject={quote("Free Lifeline scan")}">Request a free scan</a></div>')
    book = ""
    if c.get("calendar"):
        book = f'<a class="btn primary block" href="{e(c["calendar"])}">Book a 15-minute call {EXT}</a>'
    if c.get("calendar_scan"):
        book += f'<a class="btn block" href="{e(c["calendar_scan"])}">Book a free scan review {EXT}</a>'
    linkedin = f'<li><b>LinkedIn</b><a href="{e(c["linkedin"])}">Profile {EXT}</a></li>' if c.get("linkedin") else ""
    body = f"""
<section class="page-head"><div class="wrap">
  <p class="eyebrow">Contact</p><h1>Let's talk about your cloud</h1>
  <p class="lead">Tell me what hurts - the bill, the pipeline or the pager. {e(c["response"])}</p>
</div></section>
<div class="wrap contact">
  <div class="form-col"><h2>Send a message</h2>{contact_form}</div>
  <aside class="side"><div class="card">
    {book}
    <ul class="clist"><li><b>Email</b><a href="mailto:{e(c["email"])}">{e(c["email"])}</a></li>
    <li><b>Time zone</b><span>{e(data["location"])}</span></li>
    <li><b>Availability</b><span>{e(data["availability"])}</span></li>
    <li><b>GitHub</b><a href="{e(c["github"])}">ObaidAbdullah16 {EXT}</a></li>{linkedin}
    <li><b>Payment</b><span>{e(c["payments"])}</span></li></ul>
  </div></aside>
</div>
{section("free-scan", "Free", "Free ops health scan", "I run Lifeline on your public GitHub organisation and domain - domain and TLS expiry, who holds the keys, CI risks, backups - and email you a short report.", scan_form, "alt")}
"""
    return page(f'Contact - {data["name"]}', "Book a call, send a message or request a free ops health scan.",
                body, data, 0, "contact.html", "contact.html")


def thanks_page(data: dict) -> str:
    body = f"""<section class="page-head"><div class="wrap narrow">
<p class="eyebrow">Thank you</p><h1>Message received</h1>
<p class="lead">{e(data["contact"]["response"])} If it is urgent, email <a href="mailto:{e(data["contact"]["email"])}">{e(data["contact"]["email"])}</a>.</p>
<div class="actions"><a class="btn primary" href="index.html">Back to the start</a><a class="btn" href="work.html">See my work</a></div>
</div></section>"""
    return page(f'Thank you - {data["name"]}', "Your message was sent.", body, data, 0, "thanks.html")


def build() -> None:
    data = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
    if os.environ.get("SITE_URL"):  # set by scripts/up.sh after Terraform knows the URL
        data["site_url"] = os.environ["SITE_URL"]
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "site", DIST)
    (DIST / "assets" / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    pages = {"index.html": index(data), "services.html": services_page(data), "work.html": work_page(data),
             "open-source.html": open_source_page(data), "about.html": about_page(data),
             "resume.html": resume_page(data), "contact.html": contact_page(data), "thanks.html": thanks_page(data)}
    for name, content in pages.items():
        (DIST / name).write_text(content, encoding="utf-8")
    (DIST / "projects").mkdir(exist_ok=True)
    for p in data["projects"]:
        (DIST / "projects" / f'{p["slug"]}.html').write_text(project_page(p, data), encoding="utf-8")
    (DIST / "case-studies").mkdir(exist_ok=True)
    for s in data["services"]:
        (DIST / service_url(s)).write_text(service_page(s, data), encoding="utf-8")
    # Served by CloudFront for any missing path, so it uses absolute links.
    nf = '<section class="page-head"><div class="wrap"><h1>Page not found</h1><p class="lead">The page you asked for does not exist.</p><div class="actions"><a class="btn primary" href="/index.html">Back to the start</a></div></div></section>'
    (DIST / "404.html").write_text(page("Not found", "Page not found", nf, data, up="/"), encoding="utf-8")
    (DIST / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f'Sitemap: {data["site_url"].rstrip("/")}/sitemap.xml\n' if data.get("site_url") else ""), encoding="utf-8")
    if data.get("site_url"):
        base = data["site_url"].rstrip("/")
        urls = [f"{base}/"] + [f"{base}/{n}" for n in pages if n not in ("index.html", "thanks.html")]
        urls += [f'{base}/projects/{p["slug"]}.html' for p in data["projects"]]
        urls += [f'{base}/{service_url(s)}' for s in data["services"]]
        (DIST / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{e(u)}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    if not data["contact"].get("web3forms_key"):
        print("note: contact.web3forms_key is empty - the contact page shows email links instead of forms", file=sys.stderr)
    print(f"built {DIST} ({len(pages)} pages, {len(data['projects'])} project pages, {len(data['services'])} service pages)")


if __name__ == "__main__":
    build()
