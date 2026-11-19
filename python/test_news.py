"""Test the News section: its posts, and the lists made from them.

Run from the repo root::

    uv run python python/test_news.py

Every post has a date, a title and a summary; the News page, the docs' home
page and the README box are what ``packaging/update_news.py`` would write; and
every image a post shows is in the repo.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packaging"))

import update_news  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    posts = update_news.posts()
    check("there are posts", len(posts) >= 2, str(posts))
    check("newest first", [p.date for p in posts] == sorted((p.date for p in posts),
                                                            reverse=True))
    check("the Python beta note is one of them",
          any(p.stem == "2026-10-20-python-beta" for p in posts))
    for post in posts:
        text = post.path.read_text(encoding="utf-8")
        missing = [m for m in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text)
                   if not m.startswith("http") and not (post.path.parent / m).is_file()]
        check(f"{post.stem}: every image is in the repo", not missing, str(missing))
        check(f"{post.stem}: a summary short enough for the README",
              len(post.teaser) <= 240, f"{len(post.teaser)} characters")

    for path, start, end, build in update_news.TARGETS:
        expected = update_news.render(path, start, end, build(posts))
        check(f"{path.relative_to(REPO)} is up to date (packaging/update_news.py)",
              expected == path.read_text(encoding="utf-8"))

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    box = readme[readme.index("<!-- news:start -->"):readme.index("<!-- news:end -->")]
    check("the README shows at most three posts, linking to the docs site",
          0 < box.count("](https://analysis-pipeline.readthedocs.io/en/latest/news/2")
          <= update_news.README_LATEST)
    check("the old release-note path points to its new home",
          "news/2026-10-20-python-beta.html"
          in (REPO / "release_notes" / "python-beta.md").read_text(encoding="utf-8"))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
