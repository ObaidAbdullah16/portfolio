"""Build the site and check it: every relative link/asset exists, every page has a
title and description, HTML tags are balanced, and the content data is complete.

    python3 tests/check_site.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "area", "base", "col", "embed", "track", "wbr"}


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.title = False
        self.description = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "description" and a.get("content"):
            self.description = True
        if tag == "title":
            self.title = True
        for key in ("href", "src"):
            if a.get(key):
                self.links.append(a[key])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
            return
        self.stack.pop()


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "build.py")], check=True)
    problems: list[str] = []
    data = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
    slugs = {p["slug"] for p in data["projects"]}
    for s in data["services"]:
        if s["proof"] not in slugs:
            problems.append(f"service {s['id']} proof '{s['proof']}' is not a project")
    required = ("title", "summary", "situation", "problem", "solution", "flow", "plan", "evidence", "keep", "not_included")
    for s in data["services"]:
        cs = s.get("case_study")
        if not cs:
            problems.append(f"service {s['id']} has no case study")
            continue
        missing = [k for k in required if not cs.get(k)]
        if missing:
            problems.append(f"service {s['id']} case study is missing {missing}")
        elif not 3 <= len(cs["flow"]) <= 7:
            problems.append(f"service {s['id']} case study flow should have 3-7 steps")
    ids = {s["id"] for s in data["services"]}
    for sid in data.get("featured", []):
        if sid not in ids:
            problems.append(f"featured service {sid} does not exist")
    for slug in data.get("selected_work", []):
        if slug not in slugs:
            problems.append(f"selected_work {slug} is not a project")
    for key in ("headline", "availability", "photo", "proof_bar", "open_source", "resume", "faq"):
        if not data.get(key):
            problems.append(f"site.json is missing {key}")
    for s in data["services"]:
        if not s.get("short"):
            problems.append(f"service {s['id']} has no short description")
    for p in data["projects"]:
        if not p.get("short"):
            problems.append(f"project {p['slug']} has no short description")
    site_domain = urlparse(data.get("site_url", "")).hostname or ""
    if site_domain and not data["contact"]["email"].endswith("@" + site_domain):
        problems.append(f"contact.email is not on the site's domain {site_domain}")
    other = {h for h in __import__("re").findall(r"https?://([a-z0-9.-]+)", json.dumps(data)) if h.endswith(".xyz")}
    if other:
        problems.append(f"site.json links to other personal domains: {sorted(other)}")
    for p in data["projects"]:
        for sid in p.get("services", []):
            if sid not in {s["id"] for s in data["services"]}:
                problems.append(f"project {p['slug']} references unknown service {sid}")

    pages = sorted(DIST.rglob("*.html"))
    for f in pages:
        if "demos" in f.parts:  # copied reports are checked in their own repositories
            continue
        parser = Page()
        parser.feed(f.read_text(encoding="utf-8"))
        rel = f.relative_to(DIST)
        if not parser.title or not parser.description:
            problems.append(f"{rel}: missing <title> or meta description")
        if parser.stack and parser.stack != ["html"]:
            leftovers = [t for t in parser.stack if t not in ("html", "body", "head")]
            if leftovers:
                problems.append(f"{rel}: unclosed tags {leftovers}")
        problems += [f"{rel}: {err}" for err in parser.errors]
        for link in parser.links:
            u = urlparse(link)
            if u.scheme or link.startswith(("#", "mailto:")):
                continue
            path = u.path
            target = (DIST / path.lstrip("/")) if path.startswith("/") else (f.parent / path)
            if path.endswith("/"):
                target = target / "index.html"
            if not target.resolve().exists():
                problems.append(f"{rel}: broken link {link}")
    for p in problems:
        print("FAIL", p)
    print(f"checked {len(pages)} pages: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
