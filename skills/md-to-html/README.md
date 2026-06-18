# md-to-html

把 Markdown 文章渲染成**可直接发布的独立 HTML**。内置两套主题引擎，按所选主题自动切换：

- **MDNice（内联引擎 `inline`）**：30 套 MDNice 排版主题，CSS 被**内联到每个元素的 `style` 属性**上。适合**直接粘贴到公众号 / 知乎**而不掉样式。
- **Stylesheet（样式表引擎）**：开源 CSS 主题（GitHub、Sakura、LaTeX、Tufte、赫蹏、minimal 等），整段 CSS 放进 `<style>`，配语义化 HTML。适合**博客 / 独立网页 / Typora 风格发布**。

代码高亮（Pygments → highlight.js 配色）和 mermaid 流程图两套引擎共用，自动与主题配对。

---

## 安装 / 位置

技能位于本仓库 `skills/md-to-html/`。可直接用仓库内脚本运行，或安装到 Claude Code 个人技能目录后用 `/md-to-html` 调用：

```bash
# 安装到个人技能目录（全局可用）
cp -R skills/md-to-html ~/.claude/skills/md-to-html
```

依赖：Python 3。代码高亮需要 `pygments`（缺失时降级为纯文本代码块）；mermaid 在浏览器里通过 CDN 渲染。

```bash
pip install pygments    # 可选，建议安装以获得语法高亮
```

---

## 快速开始

```bash
S=skills/md-to-html/scripts/md_to_html.py

# 1) 列出所有可用主题
python3 $S list-themes

# 2) 单主题 → 干净可发布的 HTML（无 tab）
#    MDNice 主题（公众号/知乎粘贴）
python3 $S render article.md --themes 极客黑 --output article.html
#    Stylesheet 主题（博客/网页），用 slug 选
python3 $S render article.md --themes github-light --output article.html

# 3) 多主题（2–5 个）→ 带标签页的对比预览
python3 $S render article.md --themes 极客黑,橙蓝风,sakura --output preview.html

# 4) 浏览器打开
open article.html
```

主题选择符支持：MDNice 的 **ID**、**主题名**（精确或唯一子串）、stylesheet 主题的 **slug**，以及跨包重名时的 `pack:slug`。

---

## 两套引擎怎么选

| 你要发到哪 | 用哪套 | 例子 |
|---|---|---|
| 微信公众号 / 知乎（粘贴） | MDNice 内联主题 | `--themes 极客黑` |
| 博客 / 独立网页 / 静态站 | stylesheet 主题 | `--themes github-light` |
| 想对比挑主题 | 任意 2–5 个混选 | `--themes 简,sakura,latex` |

> MDNice 主题的样式被内联进元素，复制粘贴到公众号编辑器不掉格式；stylesheet 主题依赖 `<style>` 级联（含 CSS 变量、`@media` 暗色、wrapper class），**不为粘贴设计**，但更干净、适合网页。

---

## 输出模式 `--mode`

每个 **MDNice 主题都能两种方式输出**：

```bash
# inline（默认）：CSS 内联到 style 属性 —— 公众号/知乎粘贴
python3 $S render article.md --themes 极客黑 --output a.html

# stylesheet：同一套 #nice CSS 改放 <style> 块 —— HTML 更小更干净，适合网页
python3 $S render article.md --themes 极客黑 --mode stylesheet --output a.html
```

- `--mode auto`（默认）：MDNice 主题走 inline，stylesheet 主题走 stylesheet。
- stylesheet 主题是「独立样式表专属」，对它们传 `--mode inline` 会自动回退并提示（其变量/`@media` 无法忠实内联）。

---

## 代码块 & 流程图

- **代码高亮**：用 Pygments 分词成 `.hljs-*`，再叠加一套 highlight.js 配色（`atom-one-dark` / `atom-one-light` / `github` / `vs2015` / `monokai` / `dracula`），每个主题自动配一套合适的（暗色主题配暗色代码主题）。覆盖：

  ```bash
  python3 $S render article.md --themes 简 --code-theme github --output a.html
  ```

- **mermaid 流程图**：```` ```mermaid ```` 代码块渲染成真实流程图 / 时序图（仅当文档含图时才从 CDN 加载 mermaid.js）。每个主题配一套 mermaid 主题（`default`/`dark`/`forest`/`neutral`/`base`），覆盖用 `--mermaid-theme`。

  > 发布时：在浏览器打开 HTML 再复制，渲染出的 SVG 会一起被复制（与 MDNice 工作流一致）。mermaid 需要浏览器执行 JS。

- **Frontmatter**：开头的 YAML（`--- ... ---`）会被自动剥离，不会渲染成正文。

---

## 主题清单

**MDNice（30 套，内联）** —— 用主题名或 ID 选：

> 重影、丘比特忙、奇点、雁栖湖、柠檬黄、橙心、姹紫、嫩青、绿意、红绯、蓝莹、兰青、山吹、前端之巅同款、极客黑、蔷薇紫、萌绿、全栈蓝、极简黑、橙蓝风、凝夜紫、萌粉、Obsidian、灵动蓝、草原绿、科技蓝、WeFormat、简、锤子便签主题第2版、Pornhub黄

**Stylesheet（14 套，用 slug）** —— 来自 `theme-hub` 包（均 MIT）：

| 分类 | slug |
|---|---|
| 内容平台 | `github-light` `github-dark` `sakura` `water` `simple` `latex` `tufte` `typo` `smartisan` `heti` |
| 极简 | `mvp` `new` `sp` `concrete` |

> `heti`/`simple`/`latex`/`tufte`/minimal 系列会在系统暗色模式下自动转暗；`latex`/`tufte`/`heti` 的内嵌字体未随包发布，会回退系统字体。许可与出处见 `references/theme-hub/NOTICE.md`。

随时用 `list-themes` 查看实时清单：

```bash
python3 $S list-themes                 # 全部
python3 $S list-themes --query 蓝       # 按关键字过滤
python3 $S list-themes --json          # 机器可读
```

---

## 扩展：新增主题包（如 mweb-theme）

主题以**包（pack）**组织：`mdnice` 是内置内联包，`theme-hub` 是第一个扩展包。新增包**无需改代码**——放一份 `references/<pack>-themes.json` + `references/<pack>/` 即被自动发现。

用 `add-theme` 命令把一个 CSS 文件 / URL 收进某个包，自动识别 wrapper class（`.markdown-body`/`.heti`/`.typo`/classless `body`）和明暗、配对 code/mermaid 主题、登记条目（首次添加自动建包）：

```bash
# 加单个主题（CSS 路径或 http(s) URL）→ 自动创建 mweb-theme 包
python3 $S add-theme \
  --pack mweb-theme --slug mweb-gray --name "MWeb Gray" --category editor \
  --from ./mweb-gray.css --license MIT --source-url https://example.com/mweb

# 一整组批量：JSON 清单（数组，每项 {slug, name, from, category, license, ...}）
python3 $S add-theme --pack mweb-theme --manifest ./mweb.json
```

可覆盖自动识别：`--wrapper-class`（或 `none`）、`--appearance light|dark`、`--code-theme`、`--mermaid-theme`。之后用 `--themes mweb-gray` 或 `--themes mweb-theme:mweb-gray`（重名时）即可渲染。

> 收录第三方 CSS 请保留上游 license 并记录出处（填 `--license` / `--source-url`，参照 `theme-hub/NOTICE.md`）。

---

## 命令参考

| 命令 | 作用 |
|---|---|
| `list-themes [--query Q] [--json] [--with-style-only]` | 列出主题 |
| `render <md> --themes ... --output <html> [--mode] [--code-theme] [--mermaid-theme] [--preview-tabs] [--title]` | 渲染 |
| `add-theme --pack P --from CSS --slug S [...] / --manifest J` | 收录 stylesheet 主题到某个包 |
| `fetch-themes [--include-styles]` | 刷新 MDNice 主题目录（带样式需登录态） |
| `split-catalog` | 把内联了 `styleCss` 的旧目录迁移成「每主题一个 CSS 文件」 |

完整选项见 `python3 $S <command> --help`。

---

## 刷新 MDNice 主题数据

公开元数据可免登录刷新；主题 CSS 需要 MDNice 登录态：

```bash
python3 $S fetch-themes                       # 仅元数据
export MDNICE_TOKEN="..." MDNICE_OUT_ID="..." # 仅本地环境变量，切勿写进文件/产物
python3 $S fetch-themes --include-styles      # 连同 CSS
```

CSS 以**每主题一个文件**存放于 `references/mdnice-themes/`，目录 JSON 只留元数据 + `cssFile` 指针（约 20KB，不随主题增多膨胀）。

---

## 注意事项

- 单主题 = 干净可发布 HTML；2–5 主题 = 标签页对比预览（`--preview-tabs` 可强制单主题也用预览）。
- stylesheet 主题用于网页，**不要用于公众号粘贴**；公众号请用 MDNice 内联主题。
- mermaid 需浏览器执行 JS 才能出图；纯静态环境只会保留图源文本。
- 不要把 `MDNICE_TOKEN` 写进任何技能文件、引用、示例或产物。

## 相关文件

- `SKILL.md`：技能说明（供 agent 调用）。
- `scripts/md_to_html.py`：CLI 主程序。
- `references/mdnice-themes.json` + `references/mdnice-themes/`：MDNice 目录 + 每主题 CSS。
- `references/theme-hub-themes.json` + `references/theme-hub/`：stylesheet 主题包 + 出处/许可（`NOTICE.md`）。
- `references/technical-principles.md`：渲染架构、双引擎、主题包机制与已知限制。
