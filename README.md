# open-skills

一组可复用的 **Claude Code / Codex 技能（skills）** 集合。每个技能独立放在 `skills/<skill-name>/`，包含技能入口 `SKILL.md` 及其引用资源（脚本、参考文档等）。

## 技能清单

| 技能 | 说明 |
|------|------|
| [md-to-html](skills/md-to-html/) | 把 Markdown 文章渲染成可直接发布的独立 HTML。内置两套引擎：**MDNice 内联主题**（30 套，适合公众号 / 知乎粘贴）与 **stylesheet 主题包**（GitHub / Sakura / LaTeX / 赫蹏等，适合博客 / 网页）；支持代码高亮、mermaid 流程图、主题包扩展。 |

## 安装与使用

技能可直接在本仓库内用脚本运行，或安装到 Claude Code 个人技能目录后用 `/<skill-name>` 调用：

```bash
# 安装某个技能到个人技能目录（全局可用）
cp -R skills/md-to-html ~/.claude/skills/md-to-html

# 在 Claude Code 里
/md-to-html <参数>
```

每个技能的具体用法见其目录下的 `README.md` / `SKILL.md`。

## 仓库结构

```text
open-skills/
├── README.md            # 本文件（仓库总览 + 技能清单）
├── LICENSE              # 本仓库代码许可（MIT）
├── CONTRIBUTING.md      # 提交规范与目录约定
└── skills/
    └── <skill-name>/
        ├── SKILL.md     # 技能入口（必需，含 name/description frontmatter）
        ├── README.md    # 人类可读的使用指南（可选）
        ├── scripts/     # 脚本（可选）
        ├── references/  # 参考资源 / 数据（可选）
        └── tests/       # 测试（可选）
```

## 贡献

提交规范（Conventional Commits + Gitmoji）、目录约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可

本仓库自身的代码与文档以 **MIT** 许可发布，见 [LICENSE](LICENSE)。

部分技能会 vendoring 第三方开源资源（如 `md-to-html` 收录的 CSS 主题），这些资源各自保留其上游许可，出处与许可见对应目录下的 `NOTICE.md`（例如 `skills/md-to-html/references/theme-hub/NOTICE.md`）。
