---
name: md-to-html
description: Use when converting Markdown articles to clean publishable HTML with MDNice themes or standalone CSS themes (GitHub, Sakura, LaTeX, Tufte, Heti, minimal, etc.), selecting one to five themes, refreshing MDNice theme catalogs, or comparing themed Markdown renderings in tabs.
---

# md-to-html

Convert a Markdown article into standalone HTML. Two theme engines are available:

- **MDNice (`inline`)**: 30 cached MDNice layout themes. By default their CSS is converted into inline `style` attributes on an `article#nice` DOM — best for pasting into WeChat Official Account / Zhihu without losing styling.
- **Stylesheet (`stylesheet`)**: 14 standalone open-source CSS themes (GitHub Light/Dark, Sakura, Water, Simple, LaTeX, Tufte, Typo, Smartisan, Heti, MVP, new.css, sp.css, concrete) embedded verbatim in a `<style>` block over semantic HTML. Best for blogs / standalone web articles / Typora-style publishing.

Every MDNice theme can be rendered in **both** output modes via `--mode` (default `auto`): `inline` (CSS on `style` attributes; WeChat/Zhihu paste) or `stylesheet` (the same `#nice`-scoped CSS emitted as a `<style>` block; smaller, cleaner HTML for the web). Hub themes are stylesheet-only (their variable/`@media`-driven CSS can't be faithfully inlined). Default to one clean publishable HTML document for a single requested theme; use tabbed preview only when the user explicitly asks to compare or selects multiple themes. Both engines share the same Markdown parser, code highlighting, and mermaid pipeline.

## Quick Start

```bash
python3 skills/md-to-html/scripts/md_to_html.py list-themes
# MDNice inline theme (WeChat/Zhihu paste)
python3 skills/md-to-html/scripts/md_to_html.py render article.md --themes 极客黑 --output article.html
# MDNice theme as a standalone stylesheet document (web/blog instead of paste)
python3 skills/md-to-html/scripts/md_to_html.py render article.md --themes 极客黑 --mode stylesheet --output article.html
# standalone stylesheet theme (blog / web article), selected by slug
python3 skills/md-to-html/scripts/md_to_html.py render article.md --themes github-light --output article.html
python3 skills/md-to-html/scripts/md_to_html.py render article.md --themes 极客黑,橙蓝风 --output article-preview.html
# override the paired code / diagram themes
python3 skills/md-to-html/scripts/md_to_html.py render article.md --themes 简 --code-theme github --mermaid-theme neutral --output article.html
```

Theme selectors accept MDNice IDs, exact names, unique name substrings, or stylesheet-theme slugs (e.g. `github-light`, `sakura`, `latex`, `heti`). With one theme, the generated HTML is a pure article document suitable for publishing/copying into platforms such as WeChat Official Account or Zhihu. For MDNice themes, theme CSS is applied as inline `style` attributes on the generated article DOM; only the small renderer compatibility layer remains in `<style>`. With 2-5 themes, the generated HTML is a tabbed comparison preview using isolated iframes; each tab renders with its own engine.

## Standalone Stylesheet Themes

14 open-source CSS themes (vendored under `references/theme-hub/`, all MIT) render through the `stylesheet` engine: the full theme CSS is embedded verbatim in a `<style>` block over semantic HTML (plain `<h2>`, `<li>`, `<pre><code>` — no MDNice wrappers). Select by slug:

- **content platform**: `github-light`, `github-dark`, `sakura`, `water`, `simple`, `latex`, `tufte`, `typo`, `smartisan`, `heti`
- **minimal**: `mvp`, `new`, `sp`, `concrete`

These themes rely on stylesheet cascade, CSS variables, `@media (prefers-color-scheme)`, and (for some) wrapper classes, so their CSS is **not** inlined — output is for blogs / standalone web pages / Typora-style publishing, not WeChat paste. The renderer places content in the theme's required wrapper (`.markdown-body` for GitHub/Smartisan, `.heti`/`.typo` for those, plain `<body>` for classless themes) automatically. `heti`, `simple`, `latex`, `tufte`, and the minimal themes auto-switch to dark under OS dark mode; `latex`/`tufte`/`heti` declare `@font-face` with non-vendored fonts and fall back to system fonts. See `references/theme-hub/NOTICE.md` for provenance and licensing.

## Theme Packs (extending with new groups)

Themes are organised into **packs**. `mdnice` is the built-in inline pack; `theme-hub` is the first stylesheet pack. A pack is simply a convention — no code change is needed to add one:

```text
references/<pack>-themes.json   # catalog: { "themes": [ {slug, name, category, file, ...} ] }
references/<pack>/<category>/<slug>.css   # vendored CSS, `file` is relative to references/<pack>/
```

Any `references/*-themes.json` (except `mdnice`) is auto-discovered at load time. To add a new pack such as `mweb-theme`, use the `add-theme` command — it vendors the CSS, **auto-detects** the wrapper class (`.markdown-body`/`.heti`/`.typo`/classless `body`) and light/dark appearance, pairs a code/mermaid theme, and registers the entry (creating the pack on first add):

```bash
# one theme (CSS path or http(s) URL); creates references/mweb-theme-themes.json + references/mweb-theme/
python3 skills/md-to-html/scripts/md_to_html.py add-theme \
  --pack mweb-theme --slug mweb-gray --name "MWeb Gray" --category editor \
  --from ./mweb-gray.css --license MIT --source-url https://example.com/mweb

# a whole group at once via a JSON manifest (array of {slug, name, from, category, license, ...})
python3 skills/md-to-html/scripts/md_to_html.py add-theme --pack mweb-theme --manifest ./mweb.json
```

Override auto-detection with `--wrapper-class` (or `none`), `--appearance light|dark`, `--code-theme`, `--mermaid-theme`. Select a pack theme by slug, or `pack:slug` if a slug is shared across packs (e.g. `mweb-theme:github`). Vendoring third-party CSS: keep the upstream license and record provenance (add a `license`/`source-url`, mirroring `theme-hub/NOTICE.md`).

## Code Blocks and Diagrams

- **Code highlighting**: code blocks are tokenized with Pygments into `.hljs-*` spans. The code BLOCK colours (background + token colours) are a separate "highlight.js theme" dimension. The skill ships a registry of standard themes (`atom-one-dark`, `atom-one-light`, `github`, `vs2015`, `monokai`, `dracula`) and pairs each layout/stylesheet theme with a fitting one (MDNice 极客黑 → atom-one-dark, 科技蓝 → vs2015; stylesheet `github-dark` → atom-one-dark, light themes → github / atom-one-light). For MDNice themes the code CSS is inlined onto each token span (survives WeChat/Zhihu paste); for stylesheet themes it is appended as a `<style>` block scoped to the theme's wrapper so it wins the cascade and owns the code block consistently. Override with `--code-theme`.
- **Mermaid diagrams**: ` ```mermaid ` fences render as real flowcharts/sequence diagrams via mermaid.js (loaded from CDN only when a document contains diagrams), not as raw code. Each theme is paired with a mermaid theme (`default`/`dark`/`forest`/`neutral`/`base`); dark layout/stylesheet themes pair with `dark`. Override with `--mermaid-theme`. To publish, open the HTML in a browser and copy the rendered content — the SVG is copied along.
- **Footnotes**: inline links are converted to footnote references — the link text keeps a superscript `[N]` marker and the URLs are collected into a 引用链接 list at the end of the article. This is **on by default for the inline paste output** (WeChat/Zhihu strip inline link URLs, so footnotes preserve them) and **off for stylesheet documents** (web pages keep links clickable). Override with `--footnotes` / `--no-footnotes`.
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

`fetch-themes --include-styles` and `--cache-styles` store each theme's CSS as one file under `references/mdnice-themes/` and keep only a `cssFile` pointer in `mdnice-themes.json`, so the catalog stays ~20KB (metadata only) and never balloons as themes are added. To migrate an older catalog that still inlines `styleCss`, run once:

```bash
python3 skills/md-to-html/scripts/md_to_html.py split-catalog
```

## References

- `references/mdnice-themes.json`: slim MDNice catalog — metadata + per-theme `cssFile` pointer (~20KB).
- `references/mdnice-themes/`: one CSS file per MDNice theme (e.g. `13-极客黑.css`); read lazily at render time. Legacy inline `styleCss` in the catalog is still honoured.
- `references/theme-hub-themes.json`: stylesheet-engine theme catalog (slug, wrapper class, appearance, paired code/mermaid theme, license, source).
- `references/theme-hub/`: vendored CSS theme files (`content-platform/`, `minimal/`) plus `NOTICE.md` provenance/licensing.
- `references/mdnice-api.md`: endpoint notes, auth requirements, and known side effects.
- `references/technical-principles.md`: rendering architecture, both engines, MDNice-like DOM mapping, preview isolation, and known limits.
- `scripts/md_to_html.py --help`: command options.

## Common Checks

- Use one theme for clean publishable HTML. Use 2-5 themes only when the user clearly wants tabbed comparison preview.
- Choose the engine by destination: MDNice (`inline`) themes for WeChat/Zhihu paste; stylesheet themes (`github-light`, `sakura`, …) for blogs / standalone web pages.
- Code blocks and mermaid diagrams are paired to the theme automatically; only pass `--code-theme` / `--mermaid-theme` when the user wants a different pairing.
- MDNice themes default to `inline`; pass `--mode stylesheet` to emit the theme as a standalone `<style>` document for the web. Hub themes ignore `--mode inline` (stylesheet-only) and print a note.
- If an MDNice theme has no cached CSS (no `cssFile` and no inline `styleCss`), rerun with `MDNICE_TOKEN` and `MDNICE_OUT_ID`. Stylesheet themes carry CSS in vendored files and never need credentials.
- The renderer emits MDNice-like DOM hooks for the inline engine and plain semantic HTML for the stylesheet engine; it does not need generic Markdown libraries for the main conversion path.
- Inline rendering supports MDNice's cached `#nice` selectors, descendant/child/adjacent selectors, `nth-of-type`, and `::before`/`::after` content as generated inline spans. Unsupported CSS constructs are skipped instead of emitting a theme stylesheet.
