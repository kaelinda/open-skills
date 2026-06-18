# md-to-html

Render a Markdown article as standalone HTML with MDNice themes. A single selected theme produces a clean publishable HTML document. Selecting multiple themes produces a tabbed comparison preview.

## Files

- `SKILL.md`: Codex skill instructions.
- `scripts/md_to_html.py`: CLI for listing themes, refreshing theme data, and rendering previews.
- `references/mdnice-themes.json`: cached MDNice theme metadata and CSS.
- `references/mdnice-api.md`: MDNice endpoint notes and credential handling.
- `references/technical-principles.md`: rendering architecture and MDNice-like DOM mapping.

## Quick Start

List available cached themes:

```bash
python3 skills/md-to-html/scripts/md_to_html.py list-themes
```

Render a Markdown file with one theme. This produces pure article HTML without tab UI:

```bash
python3 skills/md-to-html/scripts/md_to_html.py render article.md \
  --themes 极客黑 \
  --output article.html
```

Render with multiple themes. This produces a tabbed preview for comparison:

```bash
python3 skills/md-to-html/scripts/md_to_html.py render article.md \
  --themes 极客黑,橙蓝风,兰青,橙心 \
  --output article-preview.html
```

Open the output HTML in a browser:

```bash
open article.html
```

## Output Modes

- One theme: pure standalone article HTML with one `<article id="nice">` body. The selected theme CSS is converted into inline `style` attributes; only a small renderer compatibility stylesheet remains in `<head>`. Use this for publishing or copying into WeChat Official Account, Zhihu, or similar platforms.
- Two to five themes: tabbed comparison preview with one isolated iframe per theme.
- One theme plus `--preview-tabs`: force tabbed preview for debugging.

## Theme Selection

`--themes` accepts theme IDs, exact names, or unique name substrings. You can pass comma-separated values or repeat the argument values separated by spaces.

Examples:

```bash
--themes 13,19
--themes 极客黑,橙蓝风
--themes 13 橙蓝风 兰青
```

Current cached catalog contains 30 themes with CSS:

| ID | Theme |
| --- | --- |
| 3060 | 重影 |
| 3050 | 丘比特忙 |
| 1377 | 奇点 |
| 1348 | 雁栖湖 |
| 11773 | 柠檬黄 |
| 1 | 橙心 |
| 3 | 姹紫 |
| 4 | 嫩青 |
| 5 | 绿意 |
| 6 | 红绯 |
| 8 | 蓝莹 |
| 10 | 兰青 |
| 11 | 山吹 |
| 12 | 前端之巅同款 |
| 13 | 极客黑 |
| 15 | 蔷薇紫 |
| 16 | 萌绿 |
| 17 | 全栈蓝 |
| 18 | 极简黑 |
| 19 | 橙蓝风 |
| 33 | Pornhub黄 |
| 35 | 凝夜紫 |
| 42 | 萌粉 |
| 44 | Obsidian |
| 45 | 灵动蓝 |
| 48 | 草原绿 |
| 51 | 科技蓝 |
| 62 | WeFormat |
| 63 | 简 |
| 1653 | 锤子便签主题第2版 |

## Refresh Themes

Refresh public theme metadata:

```bash
python3 skills/md-to-html/scripts/md_to_html.py fetch-themes
```

Refresh metadata and theme CSS:

```bash
export MDNICE_TOKEN="..."
export MDNICE_OUT_ID="..."
python3 skills/md-to-html/scripts/md_to_html.py fetch-themes --include-styles
```

Do not commit MDNice bearer tokens or personal article IDs. `MDNICE_OUT_ID` should point to a disposable MDNice article because the style endpoint is a `PUT` request.

## Notes

- A single render supports 1-5 themes.
- Single-theme output is clean article HTML without preview tabs or a theme stylesheet block.
- Multi-theme output uses isolated iframes so each theme's inlined article HTML remains independent.
- The renderer emits MDNice-like DOM hooks such as `.prefix`, `.content`, `.suffix`, `.table-container`, `pre.custom`, and `li > section` so cached MDNice CSS applies more closely than plain Markdown HTML.
- Theme rules are inlined for the selectors used by cached MDNice themes, including normal `#nice` selectors, descendant/child/adjacent selectors, `nth-of-type`, and generated `::before`/`::after` spans. CSS that cannot be represented as inline element styles is skipped.
- The output is intended for preview and comparison. Exact parity with the live MDNice editor can still differ where MDNice applies unpublished runtime transforms.

For a deeper implementation explanation, see `references/technical-principles.md`.
