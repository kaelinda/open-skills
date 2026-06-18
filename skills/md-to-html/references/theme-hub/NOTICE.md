# Theme Hub — Vendored Themes Notice

These CSS theme files are vendored (copied verbatim) from open-source projects so the
`md-to-html` skill can render Markdown as standalone, publishable HTML. They are used by
the `stylesheet` rendering engine (full `<style>` document over semantic HTML), which is a
separate path from the MDNice inline-style engine.

Collected via the `kaelinda/markdown-theme-hub` aggregation
(<https://github.com/kaelinda/markdown-theme-hub/tree/main/themes>); each file's true
upstream and license is listed below. All themes here are **MIT licensed**. The original
header comments inside each CSS file are preserved. For the full license text of each
project, see its upstream `LICENSE` at the linked repository.

| File | Upstream | License | Copyright |
|------|----------|---------|-----------|
| `content-platform/sakura.css` | https://github.com/oxalorg/sakura | MIT | © Mitesh Shah |
| `content-platform/water.css` | https://github.com/kognise/water.css | MIT | © Kognise |
| `content-platform/simple.css` | https://github.com/kevquirk/simple.css | MIT | © Kev Quirk |
| `content-platform/latex.css` | https://github.com/vincentdoerig/latex-css | MIT | © Vincent Dörig |
| `content-platform/tufte.css` | https://github.com/edwardtufte/tufte-css | MIT | © Edward Tufte, Dave Liepmann |
| `content-platform/typo.css` | https://github.com/sofish/typo.css | MIT | © sofish |
| `content-platform/github-light.css` | https://github.com/sindresorhus/github-markdown-css | MIT | © Sindre Sorhus |
| `content-platform/github-dark.css` | https://github.com/sindresorhus/github-markdown-css | MIT | © Sindre Sorhus |
| `content-platform/smartisan.css` | https://github.com/nihaojob/markdown-css-smartisan | MIT | © nihaojob |
| `content-platform/heti.min.css` | https://github.com/sivan/heti | MIT | © Sivan |
| `minimal/mvp.css` | https://github.com/andybrewer/mvp | MIT | © Andy Brewer |
| `minimal/new.min.css` | https://github.com/xz/new.css | MIT | © XZ |
| `minimal/sp.css` | https://github.com/susam/spcss | MIT | © Susam Pal |
| `minimal/concrete.min.css` | https://github.com/louismerlin/concrete.css | MIT | © Louis Merlin |

## Notes

- `heti`, `latex`, and `tufte` declare `@font-face` with relative font URLs that are **not**
  vendored here; browsers fall back to system fonts. The themes remain readable.
- `heti`, `simple`, `latex`, `tufte`, and the `minimal/*` themes ship a
  `@media (prefers-color-scheme: dark)` block, so they auto-switch to dark when the OS is in
  dark mode. The paired code-highlight theme is light by default; override with `--code-theme`.
- `github-light.css` and `github-dark.css` are distinct files (different content).
- The upstream `markdown-theme-hub` also shipped a `smartisan-dark.css` that is byte-identical
  to `smartisan.css`; only one copy is vendored.
