#!/usr/bin/env python3
"""Smoke tests for the md-to-html skill.

Stdlib-only (unittest); no pytest/pygments required. End-to-end cases shell out
to the CLI and write only to a temp dir, so the repo's cached catalogs/CSS are
never mutated. Run with:

    python3 skills/md-to-html/tests/test_md_to_html.py
    # or
    python3 -m unittest discover skills/md-to-html/tests
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "md_to_html.py"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import md_to_html as m  # noqa: E402

SAMPLE_MD = """\
---
title: 测试
---

# 主标题

正文 **粗体** *斜体* `code`，[链接](https://e.com)。

- A
- B

1. one
2. two

> 引用

| 列1 | 列2 |
|-----|-----|
| a | b |

```python
def f(n):
    return n * 2
```
"""


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def render(themes: str, *extra: str) -> str:
    """Render SAMPLE_MD with the given theme(s); return the output HTML."""
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "in.md"
        out = Path(tmp) / "out.html"
        md.write_text(SAMPLE_MD, encoding="utf-8")
        proc = run("render", str(md), "--themes", themes, "--output", str(out), *extra)
        if proc.returncode != 0:
            raise AssertionError(f"render {themes!r} failed: {proc.stderr}")
        return out.read_text(encoding="utf-8")


class PureHelpers(unittest.TestCase):
    def test_slugify_strips_whitespace_and_unsafe(self):
        self.assertEqual(m.slugify_theme_name("极客黑\n\n"), "极客黑")
        self.assertEqual(m.slugify_theme_name("a / b : c"), "abc")
        self.assertEqual(m.slugify_theme_name(""), "theme")

    def test_detect_appearance(self):
        self.assertEqual(m.detect_appearance("body { background-color: #1b1b1f; }"), "dark")
        self.assertEqual(m.detect_appearance("body { background-color: #ffffff; }"), "light")
        self.assertEqual(m.detect_appearance("body { color: #111; }"), "light")  # no bg -> light

    def test_detect_wrapper_class(self):
        self.assertEqual(m.detect_wrapper_class(".markdown-body h1 {}")[0], "markdown-body")
        self.assertEqual(m.detect_wrapper_class(".heti p {}")[0], "heti")
        self.assertEqual(m.detect_wrapper_class("body { color: #000; }")[0], "")  # classless
        cls, warn = m.detect_wrapper_class("#write { color:#000 }")
        self.assertEqual(cls, "")
        self.assertIsNotNone(warn)  # Typora editor DOM is flagged

    def test_frontmatter_stripped(self):
        body = m.render_markdown(SAMPLE_MD, flavor="semantic")
        self.assertNotIn("title: 测试", body)


class ThemeCatalog(unittest.TestCase):
    def test_list_has_both_engines(self):
        proc = run("list-themes", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        themes = json.loads(proc.stdout)
        engines = {t.get("engine") for t in themes}
        self.assertIn("inline", engines)
        self.assertIn("stylesheet", engines)
        self.assertGreaterEqual(sum(e == "inline" for e in (t.get("engine") for t in themes)), 1)

    def test_theme_hub_pack_discovered(self):
        self.assertIn("theme-hub", m.discover_packs())


class RenderInline(unittest.TestCase):
    def test_mdnice_inline_has_nice_dom_and_inline_styles(self):
        html = render("极客黑")
        self.assertIn('id="nice"', html)
        self.assertIn("style=", html)  # CSS inlined onto elements
        self.assertNotIn("title: 测试", html)  # frontmatter not leaked

    def test_mdnice_stylesheet_mode(self):
        html = render("极客黑", "--mode", "stylesheet")
        self.assertIn('<article id="nice">', html)
        self.assertIn("<style>", html)
        self.assertIn("#nice", html)


class RenderStylesheet(unittest.TestCase):
    def test_classless_pack_theme(self):
        html = render("sakura")
        self.assertIn("<style>", html)
        self.assertIn("<pre><code", html)         # semantic code block
        self.assertNotIn('id="nice"', html)        # no MDNice DOM
        self.assertNotIn("<li><section>", html)    # no MDNice list wrapper

    def test_wrapper_pack_theme(self):
        html = render("github-light")
        self.assertIn('<article class="markdown-body">', html)


class RenderPreview(unittest.TestCase):
    def test_multi_theme_tabs(self):
        html = render("极客黑,sakura")
        self.assertIn("tab-button", html)
        self.assertIn("<iframe", html)


class Footnotes(unittest.TestCase):
    def test_convert_links_to_footnotes_pure(self):
        body = '<p>see <a href="https://e.com/x?a=1&amp;b=2">site</a> here</p>'
        out = m.convert_links_to_footnotes(body)
        self.assertIn('<sup class="footnote-ref"', out)  # marker added
        self.assertNotIn("<a href", out)                 # link removed
        self.assertIn("引用链接", out)                    # reference list appended
        self.assertIn("site: https://e.com/x?a=1&amp;b=2", out)  # single, correct escaping
        self.assertNotIn("&amp;amp;", out)               # no double escaping

    def test_convert_links_noop_without_links(self):
        body = "<p>no links here</p>"
        self.assertEqual(m.convert_links_to_footnotes(body), body)

    def test_accent_color_prefers_footnote_ref(self):
        css = "#nice p .footnote-ref { color: rgba(239,112,96,1); } #nice p code { color: #000; }"
        self.assertEqual(m.theme_accent_color({"styleCss": css}), "rgba(239,112,96,1)")
        # falls back to the inline-code colour, then the default
        self.assertEqual(m.theme_accent_color({"styleCss": "#nice p code { color: #abc; }"}), "#abc")
        self.assertEqual(m.theme_accent_color({}), m.DEFAULT_ACCENT_COLOR)

    def test_footnote_number_color_matches_marker(self):
        import re

        html = render("极客黑")  # accent (coral), not the hardcoded default
        marker = re.search(r'<sup class="footnote-ref" style="[^"]*color:\s*([^;"]+)', html)
        number = re.search(r'<p class="footnote-item"[^>]*>\s*<span style="color:\s*([^;"]+)', html)
        self.assertIsNotNone(marker)
        self.assertIsNotNone(number)
        self.assertEqual(marker.group(1).strip(), number.group(1).strip())
        self.assertNotEqual(number.group(1).strip(), m.DEFAULT_ACCENT_COLOR)

    def test_inline_footnotes_default_on(self):
        html = render("极客黑")  # SAMPLE_MD has [链接](https://e.com)
        self.assertIn('<sup class="footnote-ref"', html)
        self.assertIn("引用链接", html)
        self.assertNotIn('<a href="https://e.com"', html)

    def test_no_footnotes_flag(self):
        html = render("极客黑", "--no-footnotes")
        self.assertNotIn('<sup class="footnote-ref"', html)
        self.assertIn('href="https://e.com"', html)  # link kept

    def test_stylesheet_footnotes_default_off(self):
        html = render("github-light")  # stylesheet engine -> footnotes off by default
        self.assertNotIn('<sup class="footnote-ref"', html)
        self.assertIn('href="https://e.com"', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
