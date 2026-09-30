"""Bedtime Manhwa website: a small static-site generator. Content in, plain HTML out, nothing to run on the server.

    python build.py              build the public site into docs/ (what GitHub Pages serves from main/docs)
    python build.py --drafts     also build content/drafts/ into preview_drafts/ (never into docs/, never pushed)

Content:
  site.json                         title, tagline, base_url (the path part is added to every link), channel_url
  content/series/<slug>.json        one per series: credits, official links, parts (status public | upcoming)
  content/articles/<slug>/index.md  published articles: front matter + markdown, images beside it
  content/drafts/<slug>/index.md    drafts (git-ignored; they may mention private uploads)
Pages: / · /<series>/ · /<series>/part-N/ · /articles/ · /articles/<slug>/ · /about/ · 404 · sitemap.xml · robots.txt

Rules built in:
  - A part only gets a video (embed, thumbnail, id) when its status is "public". Upcoming parts show no id at all.
  - After a build, every YouTube id anywhere in the output must belong to a public part, or the build fails:
    a private upload's id must never reach the public site.
  - Nothing is deleted: files a previous build wrote but this one didn't are listed, not removed.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent
YT_ID = re.compile(r"(?:youtu\.be/|[?&]v=|/embed/|/vi/|data-yt=\")([A-Za-z0-9_-]{11})")


# ---- markdown (the plain subset our articles use; no extra package needed) ------------------------------------------
def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', t)
    # bare links become links (not inside an existing tag)
    t = re.sub(r'(?<!["=>])(https?://[^\s<]+[^\s<.,;:)!?])', r'<a href="\1">\1</a>', t)
    return t


def markdown(md: str, img_prefix: str = "") -> str:
    out, para, lst, lst_kind, quote = [], [], [], None, []
    lines = md.replace("\r\n", "\n").split("\n")

    def flush():
        nonlocal para, lst, lst_kind, quote
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []
        if lst:
            out.append(f"<{lst_kind}>" + "".join(f"<li>{inline(x)}</li>" for x in lst) + f"</{lst_kind}>")
            lst, lst_kind = [], None
        if quote:
            out.append("<blockquote><p>" + inline(" ".join(quote)) + "</p></blockquote>")
            quote = []

    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        s = ln.strip()
        img = re.fullmatch(r"!\[([^\]]*)\]\(([^)\s]+)\)", s)
        if not s:
            flush()
        elif img:
            flush()
            cap = ""
            if i + 1 < len(lines) and re.fullmatch(r"\*[^*].*\*", lines[i + 1].strip()):
                cap = lines[i + 1].strip()[1:-1]
                i += 1
            src = img.group(2) if re.match(r"https?://|/", img.group(2)) else img_prefix + img.group(2)
            out.append(f'<figure><img src="{html.escape(src)}" alt="{html.escape(img.group(1))}" loading="lazy" decoding="async">'
                       + (f"<figcaption>{inline(cap)}</figcaption>" if cap else "") + "</figure>")
        elif re.fullmatch(r"-{3,}|\*{3,}", s):
            flush()
            out.append("<hr>")
        elif m := re.match(r"(#{1,4})\s+(.*)", s):
            flush()
            n = min(4, len(m.group(1)) + 1)          # the page title is the only <h1>
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif m := re.match(r"[-*]\s+(.*)", s):
            if para or quote:
                flush()
            if lst_kind not in (None, "ul"):
                flush()
            lst_kind = "ul"
            lst.append(m.group(1))
        elif m := re.match(r"\d+[.)]\s+(.*)", s):
            if para or quote:
                flush()
            if lst_kind not in (None, "ol"):
                flush()
            lst_kind = "ol"
            lst.append(m.group(1))
        elif s.startswith(">"):
            if para or lst:
                flush()
            quote.append(s.lstrip("> "))
        else:
            if lst and ln.startswith("  "):           # a list item carried onto the next line
                lst[-1] += " " + s
            else:
                if lst or quote:
                    flush()
                para.append(s)
        i += 1
    flush()
    return "\n".join(out)


def front_matter(text: str):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    meta = {}
    for ln in text[3:end].strip().splitlines():
        k, _, v = ln.partition(":")
        meta[k.strip()] = v.strip()
    return meta, text[end + 4:].lstrip("\n")


def plain(md_or_html: str, limit: int = 158) -> str:
    t = re.sub(r"<[^>]+>", " ", md_or_html)
    t = re.sub(r"[*_`#>\[\]!]|\(https?://[^)]+\)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= limit else t[:limit - 1].rsplit(" ", 1)[0] + "…"


# ---- build -----------------------------------------------------------------------------------------------------------
class Site:
    def __init__(self, drafts: bool = False):
        self.cfg = json.loads((HERE / "site.json").read_text(encoding="utf-8"))
        self.base_url = self.cfg["base_url"].rstrip("/")
        self.base = urlparse(self.base_url).path.rstrip("/")          # "/bedtime-manhwa-site"
        self.drafts = drafts
        self.out = HERE / ("preview_drafts" if drafts else "docs")
        self.env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]),
                               trim_blocks=True, lstrip_blocks=True)
        self.written: list[str] = []
        self.pages: list[tuple[str, str]] = []                        # (path, lastmod) for the sitemap
        self.series = self.load_series()
        self.articles = self.load_articles()
        self.public_ids = {p["youtube_id"] for s in self.series for p in s["parts"] if p.get("youtube_id")}

    # links and urls
    def link(self, path: str) -> str:
        return self.base + "/" + path.lstrip("/")

    def abs(self, path: str) -> str:
        return self.base_url + "/" + path.lstrip("/")

    def load_series(self):
        out = []
        for f in sorted((HERE / "content" / "series").glob("*.json")):
            s = json.loads(f.read_text(encoding="utf-8"))
            s["slug"] = f.stem
            for p in s["parts"]:
                if p.get("status") != "public":
                    if p.get("youtube_id"):
                        raise SystemExit(f"{f.name} part {p['n']}: an upcoming part must not carry a youtube_id "
                                         "(the id of an unlisted/private upload would leak)")
                    p["youtube_id"] = None
                p["slug"] = f"part-{p['n']}"
                p["path"] = f"{s['slug']}/{p['slug']}/"
                p["title"] = f"{s['title']} Recap Part {p['n']} (Episodes {p['episodes']})"
            out.append(s)
        return sorted(out, key=lambda s: s.get("order", 99))

    def load_articles(self):
        roots = [HERE / "content" / "articles"] + ([HERE / "content" / "drafts"] if self.drafts else [])
        out = []
        for root in roots:
            for f in sorted(root.glob("*/index.md")):
                meta, body = front_matter(f.read_text(encoding="utf-8"))
                is_draft = root.name == "drafts" or meta.get("status") != "published"
                if is_draft and not self.drafts:
                    continue
                slug = f.parent.name
                a = dict(meta, slug=slug, dir=f.parent, draft=is_draft, path=f"articles/{slug}/")
                a["html"] = markdown(body)
                a["description"] = meta.get("description") or plain(a["html"])
                a["image_url"] = self.abs(a["path"] + meta["image"]) if meta.get("image") else None
                a["part"] = int(meta["part"]) if meta.get("part") else None
                out.append(a)
        return sorted(out, key=lambda a: (a.get("date") or "9999", a["slug"]), reverse=True)

    def render(self, template: str, path: str, **ctx):
        ctx.setdefault("canonical", self.abs(path))
        ctx.setdefault("og_image", self.abs("static/img/og-default.png"))
        ctx.setdefault("og_type", "website")
        page = self.env.get_template(template).render(site=self.cfg, link=self.link, absurl=self.abs, series_list=self.series,
                                                      drafts=self.drafts, year=date.today().year, **ctx)
        dst = self.out / path / "index.html" if not path.endswith(".html") else self.out / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(page, encoding="utf-8")
        self.written.append(str(dst.relative_to(self.out)).replace("\\", "/"))
        if not path.endswith("404.html") and not ctx.get("noindex"):
            self.pages.append((path, ctx.get("lastmod") or date.today().isoformat()))

    def article_for(self, s, p):
        return next((a for a in self.articles if a.get("series") == s["slug"] and a["part"] == p["n"]), None)

    def build(self):
        self.out.mkdir(parents=True, exist_ok=True)
        before = {str(p.relative_to(self.out)).replace("\\", "/") for p in self.out.rglob("*") if p.is_file()}
        # static files
        for f in (HERE / "static").rglob("*"):
            if f.is_file():
                d = self.out / "static" / f.relative_to(HERE / "static")
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, d)
                self.written.append(str(d.relative_to(self.out)).replace("\\", "/"))
        latest = [(s, p) for s in self.series for p in reversed(s["parts"]) if p["status"] == "public"]
        self.render("home.html", "", title=f"{self.cfg['title']}: {self.cfg['tagline']}", description=self.cfg["description"],
                    latest=latest[:6], articles=self.articles[:4], home=True,
                    og_image=(f"https://i.ytimg.com/vi/{latest[0][1]['youtube_id']}/maxresdefault.jpg" if latest else None)
                    or self.abs("static/img/og-default.png"))
        for s in self.series:
            arts = [a for a in self.articles if a.get("series") == s["slug"]]
            pub = [p for p in s["parts"] if p["status"] == "public"]
            og = (f"https://i.ytimg.com/vi/{pub[0]['youtube_id']}/maxresdefault.jpg" if pub
                  else next((a["image_url"] for a in arts if a["image_url"]), None))
            self.render("series.html", s["slug"] + "/", title=f"{s['title']} Recap: Every Part in Order | {self.cfg['title']}",
                        description=plain(s["description"]), s=s, articles=arts, **({"og_image": og} if og else {}))
            for p in s["parts"]:
                art = self.article_for(s, p)
                og = (f"https://i.ytimg.com/vi/{p['youtube_id']}/maxresdefault.jpg" if p["youtube_id"]
                      else (art["image_url"] if art and art["image_url"] else None))
                self.render("part.html", p["path"], title=f"{p['title']} | {self.cfg['title']}", description=plain(p["summary"]),
                            s=s, p=p, article=art, og_type="video.other" if p["youtube_id"] else "website",
                            noindex=not p["youtube_id"],        # a "coming soon" page is too thin to index yet
                            **({"og_image": og} if og else {}))
        self.render("articles.html", "articles/", title=f"Articles | {self.cfg['title']}",
                    description="Spoiler-light companion articles to our manhwa recaps, with credits and official links.",
                    articles=self.articles)
        for a in self.articles:
            for img in a["dir"].iterdir():
                if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    d = self.out / a["path"] / img.name
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(img, d)
                    self.written.append(str(d.relative_to(self.out)).replace("\\", "/"))
            s = next((x for x in self.series if x["slug"] == a.get("series")), None)
            p = next((x for x in (s["parts"] if s else []) if x["n"] == a["part"]), None)
            self.render("article.html", a["path"], title=f"{a['title']} | {self.cfg['title']}", description=plain(a["description"]),
                        a=a, s=s, p=p, og_type="article", lastmod=a.get("date"),
                        **({"og_image": a["image_url"]} if a["image_url"] else {}))
        self.render("about.html", "about/", title=f"About | {self.cfg['title']}",
                    description=f"Who makes {self.cfg['title']}, how we credit creators, and where to watch.")
        self.render("404.html", "404.html", title=f"Page not found | {self.cfg['title']}", description="This page doesn't exist.",
                    canonical=self.abs(""))
        (self.out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{self.abs(p)}</loc><lastmod>{m}</lastmod></url>\n" for p, m in self.pages)
            + "</urlset>\n", encoding="utf-8")
        (self.out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {self.abs('sitemap.xml')}\n", encoding="utf-8")
        (self.out / ".nojekyll").write_text("", encoding="utf-8")   # Pages serves the files as they are
        self.written += ["sitemap.xml", "robots.txt", ".nojekyll"]
        self.check_ids()
        stale = sorted(before - set(self.written))
        print(f"built {len(self.pages)} pages into {self.out.name}/ ({len(self.articles)} articles"
              + (", drafts included" if self.drafts else "") + ")")
        if stale:
            print("not written by this build (left in place; move to _HOLDING if they should go):\n  " + "\n  ".join(stale))

    def check_ids(self):
        """Every YouTube id in the output must be a public part's. Stops the build otherwise."""
        bad = {}
        for f in self.out.rglob("*"):
            if f.suffix in (".html", ".xml", ".txt", ".js", ".json"):
                for vid in YT_ID.findall(f.read_text(encoding="utf-8", errors="replace")):
                    if vid not in self.public_ids:
                        bad.setdefault(vid, []).append(str(f.relative_to(self.out)))
        if bad and not self.drafts:
            raise SystemExit("STOP: the output mentions YouTube ids that are not public parts (a private upload would leak): "
                             + "; ".join(f"{k} in {', '.join(v[:3])}" for k, v in bad.items()))
        if bad:
            print("drafts preview mentions non-public ids (fine here, never in docs/): " + ", ".join(bad))


if __name__ == "__main__":
    Site(drafts="--drafts" in sys.argv).build()
