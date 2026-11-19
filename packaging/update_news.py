"""Write the news lists from the posts in ``docs/news/``.

Run from the repo root after adding or editing a post::

    uv run python packaging/update_news.py          # rewrite
    uv run python packaging/update_news.py --check  # fail if out of date

A post is ``docs/news/YYYY-MM-DD-<slug>.md``, starting with::

    ---
    date: 2026-11-19
    summary: One or two sentences for the lists.
    headline: (optional) the README's title for it, if not the post's own
    teaser: (optional) the README's sentence for it, if not the summary
    ---

    # Its title

Three places list the posts, between ``news:start`` and ``news:end`` markers,
and this keeps them in step:

* ``docs/news/index.md``: every post, newest first;
* ``docs/index.rst``: the latest one, at the top of the docs' home page;
* ``README.md``: the latest three, at the top, linking to the docs site
  (GitHub renders the README, so the links are to the published pages).
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NEWS = REPO / "docs" / "news"
SITE = "https://analysis-pipeline.readthedocs.io/en/latest"
README_LATEST = 3

_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_POST = re.compile(r"^\d{4}-\d{2}-\d{2}-.+\.md$")


@dataclass(frozen=True)
class Post:
    path: Path
    date: dt.date
    title: str
    summary: str
    #: The README's words for it, which can be shorter or livelier than the
    #: docs' (the title and summary, unless the post says otherwise).
    headline: str = ""
    teaser: str = ""

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def url(self) -> str:
        return f"{SITE}/news/{self.stem}.html"

    @property
    def day(self) -> str:
        return f"{self.date.day} {self.date:%B %Y}"

    @property
    def short_day(self) -> str:
        return f"{self.date.day} {self.date:%b %Y}"


def read_post(path: Path) -> Post:
    text = path.read_text(encoding="utf-8")
    front = _FRONT.match(text)
    if not front:
        raise ValueError(f"{path.name}: no front matter (date, summary)")
    fields = {}
    for line in front.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    for key in ("date", "summary"):
        if not fields.get(key):
            raise ValueError(f"{path.name}: front matter has no {key}")
    date = dt.date.fromisoformat(fields["date"])
    if not path.name.startswith(date.isoformat()):
        raise ValueError(f"{path.name}: the name should start with its date, {date}")
    title = next((line[2:].strip() for line in text[front.end():].splitlines()
                  if line.startswith("# ")), "")
    if not title:
        raise ValueError(f"{path.name}: no '# Title' line")
    return Post(path, date, title, fields["summary"],
                headline=fields.get("headline") or title,
                teaser=fields.get("teaser") or fields["summary"])


def posts() -> list[Post]:
    """Every post, newest first."""
    found = [read_post(p) for p in NEWS.glob("*.md") if _POST.match(p.name)]
    return sorted(found, key=lambda p: (p.date, p.stem), reverse=True)


# ── The three lists ──────────────────────────────────────────────────────────

def news_index(items: list[Post]) -> str:
    return "\n".join(
        f"## [{p.title}]({p.stem}.md)\n\n*{p.day}*\n\n{p.summary}\n" for p in items)


def docs_home(items: list[Post]) -> str:
    latest = items[0]
    return (".. tip::\n\n"
            f"   **News, {latest.day}:** :doc:`{latest.title} <news/{latest.stem}>`. "
            f"{latest.summary} :doc:`All news <news/index>`\n")


def readme(items: list[Post]) -> str:
    lines = ["> [!NOTE]",
             f"> **Latest news** · [all news]({SITE}/news/index.html)",
             ">"]
    for p in items[:README_LATEST]:
        lines.append(f"> - **[{p.headline}]({p.url})** ({p.short_day}): {p.teaser}")
    lines += [
        ">",
        f"> [**Download the app**]({SITE}/python/installation.html#the-desktop-app-easiest)"
        f" (Windows, Mac) · [**Install from source**]({SITE}/python/installation.html"
        f"#from-the-source-code) · [**Quickstart**]({SITE}/python/quickstart.html)"
        f" · [**MATLAB vs Python**]({SITE}/python/matlab-vs-python.html)"
        " · [**Send us feedback**](https://github.com/SAND-Lab/MEA-NAP/discussions)",
    ]
    return "\n".join(lines) + "\n"


#: (file, start marker, end marker, what goes between them)
TARGETS = (
    (NEWS / "index.md", "<!-- news:start -->", "<!-- news:end -->", news_index),
    (REPO / "docs" / "index.rst", ".. news:start", ".. news:end", docs_home),
    (REPO / "README.md", "<!-- news:start -->", "<!-- news:end -->", readme),
)


def render(path: Path, start: str, end: str, body: str) -> str:
    text = path.read_text(encoding="utf-8")
    a, b = text.find(start), text.find(end)
    if a < 0 or b < a:
        raise ValueError(f"{path.relative_to(REPO)}: no {start} … {end} markers")
    return text[: a + len(start)] + "\n\n" + body + "\n" + text[b:]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    items = posts()
    if not items:
        print("No posts in docs/news/.")
        return 1
    stale = []
    for path, start, end, build in TARGETS:
        new = render(path, start, end, build(items))
        if new != path.read_text(encoding="utf-8"):
            stale.append(path.relative_to(REPO))
            if not check:
                path.write_text(new, encoding="utf-8")
    if check and stale:
        print("Out of date (run packaging/update_news.py): "
              + ", ".join(map(str, stale)))
        return 1
    print(("Up to date: " if check or not stale else "Updated: ")
          + ", ".join(str(t[0].relative_to(REPO)) for t in TARGETS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
