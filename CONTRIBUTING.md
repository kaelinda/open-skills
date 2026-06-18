# 开发规范（Contributing）

> 本仓库是 Claude Code 的 skills（技能）集合。每个技能位于 `skills/<skill-name>/` 目录下，通常包含 `SKILL.md` 及其引用资源。

## 一、提交规范

本仓库遵循 **Conventional Commits + Gitmoji**。提交信息格式如下：

```
<type>(<scope>): <emoji> <subject>
```

- `<scope>` 可选（影响范围 / 模块名），整体改动可省略。
- `<emoji>` 与 `<type>` **固定对应**（见下表），写在 `:` 之后、`<subject>` 之前。
- `<subject>` 使用**中文**，简明描述本次改动。

### 提交类型与 emoji 对照

| type | 说明 | emoji |
|------|------|-------|
| feat | 新功能 | ✨ |
| fix | 修复 bug | 🐛 |
| docs | 文档 | 📝 |
| style | 格式（不影响逻辑） | 💄 |
| refactor | 重构 | ♻️ |
| perf | 性能 | ⚡ |
| test | 测试 | ✅ |
| build | 构建 / 依赖 | 📦 |
| ci | CI 配置 | 🎡 |
| chore | 杂务 | 🔧 |
| revert | 回退 | ⏪ |

### 示例

```
feat(auth): ✨ 新增用户登录功能
fix(api): 🐛 修复请求超时问题
docs: 📝 更新 README 安装说明
```

### 辅助工具

可配合 `smart-git-commit` 类技能自动生成符合本规范的提交信息（拆分原子提交、暂存区检查等）。

## 二、目录约定

- 每个技能独立放在 `skills/<skill-name>/`。
- 技能入口为该目录下的 `SKILL.md`（含 `name` / `description` frontmatter）；引用资源放在子目录（如 `references/`、`scripts/`、`assets/`）。
- 与具体技能无关的仓库级文档放在仓库根目录。

## 三、测试与 CI

- 技能的测试放在 `skills/<skill-name>/tests/`，用标准库 `unittest`（免额外依赖），可单独运行：

  ```bash
  python3 -m unittest discover -s skills/<skill-name>/tests
  ```

- CI（`.github/workflows/ci.yml`）会在 push / PR 时对 `skills/` 下脚本做字节编译，并自动发现并运行每个技能的 `tests/` 套件。新增技能时按同样约定放置测试即可被纳入。
