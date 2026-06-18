---
name: md-to-html
description: Use when converting Markdown articles to clean publishable HTML with MDNice themes, selecting one to five themes, refreshing MDNice theme catalogs, or comparing themed Markdown renderings in tabs.
---

# md-to-html

Convert a Markdown article into standalone HTML using MDNice themes. Default to one clean publishable HTML document for a single requested theme; use tabbed preview only when the user explicitly asks to compare or selects multiple themes.

## Quick Start

```bash
python3 skills/md-to-html/scripts/md_to_html.py list-themes
python3 skills/md-to-html/scripts/md_to_html.py render article.md --themes 极客黑 --output article.html
python3 skills/md-to-html/scripts/md_to_html.py render article.md --themes 极客黑,橙蓝风 --output article-preview.html
# override the paired code / diagram themes
python3 skills/md-to-html/scripts/md_to_html.py render article.md --themes 简 --code-theme github --mermaid-theme neutral --output article.html
```

Theme selectors accept IDs, exact names, or unique name substrings. With one theme, the generated HTML is a pure article document suitable for publishing/copying into platforms such as WeChat Official Account or Zhihu. Theme CSS is applied as inline `style` attributes on the generated article DOM; only the small renderer compatibility layer remains in `<style>`. With 2-5 themes, the generated HTML is a tabbed comparison preview using isolated iframes, and each iframe uses the same inline article rendering.

## Code Blocks and Diagrams

- **Code highlighting**: MDNice layout themes only colour inline `code`; the code BLOCK (background + `.hljs-*` token colours) is a separate "highlight.js theme" dimension. The skill ships a registry of standard highlight.js themes (`atom-one-dark`, `atom-one-light`, `github`, `vs2015`, `monokai`, `dracula`) and pairs each layout theme with a fitting one (e.g. 极客黑 → atom-one-dark, 科技蓝 → vs2015, 简 → github, 姹紫 → dracula). The code CSS is appended after the layout CSS and inlined onto each token span, so it survives WeChat/Zhihu paste. Override with `--code-theme`.
- **Mermaid diagrams**: ` ```mermaid ` fences render as real flowcharts/sequence diagrams via mermaid.js (loaded from CDN only when a document contains diagrams), not as raw code. Each layout theme is paired with a mermaid theme (`default`/`dark`/`forest`/`neutral`/`base`). Override with `--mermaid-theme`. To publish, open the HTML in a browser and copy the rendered content — the SVG is copied along, the same workflow MDNice uses.
- **Frontmatter**: a leading YAML frontmatter block (`--- ... ---`) is stripped, not rendered as body text.

## Refresh Theme Data

Public theme metadata can be refreshed without login:

```bash
python3 skills/md-to-html/scripts/md_to_html.py fetch-themes
```

Theme CSS requires MDNice login credentials and an article `outId` because MDNice exposes it through `PUT /articles/styles`:

```bash
export MDNICE_TOKEN="..."
export MDNICE_OUT_ID="..."
python3 skills/md-to-html/scripts/md_to_html.py fetch-themes --include-styles
```

Never write MDNice bearer tokens into skill files, references, command examples, or final artifacts.

## References

- `references/mdnice-themes.json`: cached theme metadata and any CSS that was reachable when refreshed.
- `references/mdnice-api.md`: endpoint notes, auth requirements, and known side effects.
- `references/technical-principles.md`: rendering architecture, MDNice-like DOM mapping, preview isolation, and known limits.
- `scripts/md_to_html.py --help`: command options.

## Common Checks

- Use one theme for clean publishable HTML. Use 2-5 themes only when the user clearly wants tabbed comparison preview.
- Code blocks and mermaid diagrams are paired to the layout theme automatically; only pass `--code-theme` / `--mermaid-theme` when the user wants a different pairing.
- If a theme has no cached CSS, rerun with `MDNICE_TOKEN` and `MDNICE_OUT_ID`, or pick a theme that has `styleCss` in the catalog.
- The renderer emits MDNice-like DOM hooks locally; it does not need generic Markdown libraries for the main conversion path.
- Inline rendering supports MDNice's cached `#nice` selectors, descendant/child/adjacent selectors, `nth-of-type`, and `::before`/`::after` content as generated inline spans. Unsupported CSS constructs are skipped instead of emitting a theme stylesheet.
