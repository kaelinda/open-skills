# Technical Principles

`md-to-html` converts Markdown into standalone HTML. It has **two rendering engines**, chosen automatically from the selected theme:

- **`inline` (MDNice)**: approximates MDNice's editor output. It emits MDNice-like DOM hooks and converts cached MDNice theme CSS into inline `style` attributes on an `article#nice` DOM, so the result survives a WeChat/Zhihu paste.
- **`stylesheet` (theme hub)**: renders plain semantic HTML and embeds a vendored open-source CSS theme verbatim in a `<style>` block. This is for blogs / standalone web pages / Typora-style publishing, where the cascade, CSS variables, `@media`, and wrapper classes are needed and inlining would destroy them.

Both engines share one Markdown parser (`render_markdown(text, flavor=...)`), one Pygments-based code highlighter, and one mermaid pipeline. `build_theme_document` dispatches a theme to the right engine and renders the matching Markdown flavor (`mdnice` wrappers vs `semantic`).

## Pipeline

```text
Markdown file
  -> local Markdown parser
  -> MDNice-like article DOM
  -> single-theme publish HTML
  -> optional tabbed preview shell for multi-theme comparison
```

For one theme, the generated file is a pure article HTML document containing:

- base compatibility CSS
- one cached MDNice theme CSS string converted into inline `style` attributes
- one `<article id="nice">...</article>` body

For multiple themes, the generated preview contains a host page with tabs. Each tab owns one `iframe` whose `srcdoc` contains:

- base preview CSS
- one article whose cached MDNice theme CSS has been converted into inline `style` attributes
- one `<article id="nice">...</article>` body

Using iframes in multi-theme mode prevents one theme's `#nice` rules from leaking into another theme. Single-theme mode avoids the host shell and iframe so the output is easier to publish or copy into article platforms.

## Theme Data

Theme metadata comes from:

```http
GET https://api.mdnice.com/themes?pageSize=100&currentPage=1
```

Theme CSS comes from:

```http
PUT https://api.mdnice.com/articles/styles
```

The style endpoint requires `MDNICE_TOKEN` and `MDNICE_OUT_ID`.

CSS is **not** inlined into the catalog JSON. Each theme's CSS is stored as one file under `references/mdnice-themes/` (e.g. `13-极客黑.css`), and `mdnice-themes.json` keeps only metadata plus a `cssFile` pointer (~450 bytes/theme, ~20KB total). This is because `styleCss` was ~98% of the old monolithic catalog (>1.2MB); externalizing it keeps the catalog small, makes per-theme diffs clean, and mirrors the `theme-hub` layout. At render time `hydrate_theme_css` reads the `cssFile` back into memory (an inline `styleCss` still wins for backward compatibility). `split-catalog` migrates an older inline catalog; `fetch-themes --include-styles` and `--cache-styles` write per-theme files going forward via `externalize_theme_css`.

### MDNice output modes

`--mode` selects how an MDNice theme is emitted (`build_theme_document`):

- `inline` (default): `inline_theme_article` flattens the `#nice`-scoped CSS onto each element's `style` attribute (survives WeChat/Zhihu paste).
- `stylesheet`: `mdnice_stylesheet_document` keeps the same `#nice` DOM but emits the CSS verbatim in a `<style>` block (smaller, cleaner HTML for the web). Mermaid is left intact in both cases — the inline path extracts/splices it around the inliner, and the stylesheet path never runs the inliner.

Hub (`stylesheet`-engine) themes are stylesheet-only; `--mode inline` on them falls back to stylesheet with a note, because their `:root` variables and `@media` rules cannot be represented as inline element styles.

## Why Plain Markdown HTML Is Not Enough

MDNice themes include selectors like:

```css
#nice h2 .prefix
#nice h2 .content
#nice h2 .suffix
#nice .table-container table
#nice pre.custom code
#nice ul li section
```

Plain Markdown renderers usually emit simpler HTML:

```html
<h2>Title</h2>
<table>...</table>
<pre><code>...</code></pre>
<ul><li>Item</li></ul>
```

That structure misses many selectors used by MDNice themes. `md-to-html` therefore renders common Markdown blocks into MDNice-like wrappers.

## DOM Mapping

Headings:

```html
<h2>
  <span class="prefix"></span>
  <span class="content">Title</span>
  <span class="suffix"></span>
</h2>
```

Tables:

```html
<section class="table-container">
  <table>...</table>
</section>
```

Code blocks:

```html
<pre class="custom"><code class="language-js">...</code></pre>
```

Lists:

```html
<ul>
  <li><section>Item</section></li>
</ul>
```

Blockquotes:

```html
<blockquote>
  <p>Quote</p>
</blockquote>
```

Paragraph soft breaks are preserved as `<br>` so field-style reports do not collapse multiple lines into one paragraph line.

## Theme Inlining

Cached MDNice theme CSS is not emitted as a theme `<style>` block. During rendering, `md-to-html` parses the selected theme CSS, matches supported selectors against the generated `article#nice` DOM, and writes the declarations directly onto each matching element's inline `style` attribute.

The inliner supports the selector shapes used by the cached MDNice themes:

- `#nice` root selectors
- descendant, child, and adjacent-sibling selectors
- class, id, and tag selectors
- `nth-of-type`, `first-child`, and `last-child`
- terminal `::before` and `::after`, represented as generated `<span data-mdnice-pseudo="before|after">` nodes

CSS constructs that cannot be represented as inline element styles, or selectors outside the supported MDNice subset, are skipped rather than emitted as a theme stylesheet. The output still keeps a small compatibility `<style>` block for page reset, responsive media behavior, tables, images, and code-highlight fallback colors.

## Stylesheet Engine (Theme Hub)

`stylesheet`-engine themes are vendored open-source CSS files under `references/theme-hub/`, catalogued in `references/theme-hub-themes.json` (`slug`, `category`, `file`, `wrapperClass`, `appearance`, `codeTheme`, `mermaidTheme`, `license`, `source`). They are the inverse of the inline engine: instead of flattening CSS onto elements, `stylesheet_document` emits the theme CSS **verbatim** in a `<style>` block over plain semantic HTML. This is required because these themes depend on stylesheet-only behaviour — the cascade, `:root` CSS variables, `@media (prefers-color-scheme: dark)`, `@font-face`, and wrapper-class scoping — none of which can be inlined.

DOM differs from the inline engine because `render_markdown(text, flavor="semantic")` is used:

- headings are bare `<h2>…</h2>` (no `.prefix/.content/.suffix` spans)
- list items are bare `<li>…</li>` (no `<section>` wrapper)
- code blocks are `<pre><code class="hljs language-x">…</code></pre>` with **literal** newlines and spaces (no `<br>`/`&nbsp;`), because stylesheet themes render code under `white-space: pre`
- tables are plain `<table>` inside a style-only `overflow-x` scroll box

Content is placed in the theme's required wrapper: `wrapperClass` empty → directly in `<body>` (classless themes like sakura/water/simple/minimal); `markdown-body` → `<article class="markdown-body">` (GitHub, Smartisan); `heti`/`typo` → those classes. The document layers three `<style>` blocks: a minimal reset (so the theme wins), the theme CSS, then the paired code-highlight CSS.

## Code Highlighting

Fenced code blocks are tokenized with Pygments, and each token is wrapped in a
`<span class="hljs-*">` (Pygments token types are mapped onto highlight.js class
names via `HLJS_CLASS_RULES`). In the `inline` (MDNice) engine, newlines become
`<br>` and spaces `&nbsp;` so the layout themes' `display:-webkit-box` on `<code>`
cannot collapse the lines. In the `stylesheet` engine, newlines and spaces are kept
literal (`code_escape(..., semantic=True)`) and the block renders under
`white-space: pre`. If Pygments is unavailable, code falls back to escaped plain
text with the same line/space handling.

For the `stylesheet` engine, `build_code_theme_css_semantic` emits the paired code
theme scoped to the theme's wrapper (`.markdown-body pre …` or `body pre …`),
appended after the theme CSS so it wins the cascade and owns the code block
(background + base text + `.hljs-*` token colours). Light themes pair with a light
code theme (`github`/`atom-one-light`), dark themes with `atom-one-dark`.

The cached layout themes style only inline `code`; the code BLOCK (background and
`.hljs-*` token colours) is a separate dimension — MDNice composes a highlight.js
"code theme" on top of the layout theme. The catalog never captured those, so the
skill ships its own registry (`CODE_THEMES`): `atom-one-dark`, `atom-one-light`,
`github`, `vs2015`, `monokai`, `dracula`. Each is a compact role→colour map
(`HLJS_ROLE_CLASSES` maps hljs classes to roles) expanded by `build_code_theme_css`
into `#nice pre.custom`-scoped CSS. `THEME_STYLE_MAP` pairs every layout theme with
a fitting code theme; `--code-theme` overrides it. The code CSS is appended AFTER
the layout CSS so the inliner turns it into inline styles (surviving WeChat/Zhihu
paste) and its high-specificity `#nice pre.custom` rules beat the layout theme's
plain `pre`/`code` rules.

## Mermaid Diagrams

A ` ```mermaid ` fence is not a code block — it is routed to `render_mermaid_block`,
which emits `<div class="mermaid">…escaped source…</div>` inside a marker
`<section data-mermaid="1">`. Before theme inlining, `extract_mermaid_blocks`
swaps each marker section for a plain-text token so the inliner cannot mutate the
diagram source; the sections are spliced back verbatim afterwards. When a document
contains diagrams, `mermaid_runtime` injects mermaid.js (ESM, from CDN) into the
`<head>`, which renders each `.mermaid` element to SVG on load. `THEME_STYLE_MAP`
also pairs each layout theme with a mermaid theme (`default`/`dark`/`forest`/
`neutral`/`base`); `--mermaid-theme` overrides it. To publish, open the HTML in a
browser and copy — the rendered SVG is copied along, matching MDNice's workflow.

## Frontmatter

`strip_frontmatter` removes a leading YAML frontmatter block (`--- ... ---`) before
parsing, so metadata lines do not render as a stray paragraph (the opening `---`
would otherwise be parsed as an `<hr>`). It also runs before title derivation.

## Output Modes

Single-theme mode is the default for publishable output:

```text
HTML document
  -> compatibility style block
  -> article#nice with inline theme styles
```

Multi-theme mode is for visual comparison:

```text
Host HTML
  -> tabs
  -> iframe(theme A article with inline theme styles)
  -> iframe(theme B article with inline theme styles)
```

## Preview Isolation

In multi-theme mode, the host HTML is intentionally separate from article HTML:

- Host page: tab controls, iframe layout, keyboard/browser scrolling behavior.
- Iframe page: MDNice article body with the selected theme already inlined.

This design keeps theme comparison predictable. Without iframes, every theme would target the same `#nice` selectors and later CSS blocks would override earlier ones. Single-theme output skips this layer because there is no competing theme CSS.

## Refresh Behavior

`fetch-themes` refreshes the public catalog. If an existing catalog already has `styleCss`, the script preserves it during metadata-only refreshes so a no-auth refresh does not accidentally erase cached styles.

`fetch-themes --include-styles` refreshes CSS by calling the authenticated style endpoint once per visible theme.

## Limits

This implementation is a close local preview, not a byte-for-byte clone of MDNice's live editor. Differences can remain when MDNice applies private runtime transforms, custom plugins, editor-only layout rules, upload handling, image hosting transforms, or unsupported Markdown extensions.

The local parser currently focuses on common article Markdown:

- headings
- paragraphs and soft breaks
- unordered and ordered lists
- blockquotes
- fenced code blocks (with paired highlight.js code theme)
- mermaid diagrams (rendered client-side via mermaid.js)
- tables
- horizontal rules
- inline code, emphasis, strong text, links, and images

Nested lists and uncommon Markdown extensions may render differently from MDNice.
Mermaid diagrams need a browser to render (mermaid.js from CDN); a no-JS static
SVG export would require a local mermaid renderer, which is not bundled.
