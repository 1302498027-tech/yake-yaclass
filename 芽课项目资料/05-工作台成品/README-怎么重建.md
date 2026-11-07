# 芽课个人工作库 · 怎么重建

## 每天自动跑

已经有一条自动化：**每天 08:30** 跑 `daily_push.py`，把工作台重建、上线、推一封邮件到 `1302498027@qq.com`。

```bash
python daily_push.py               # 重建 + 发布 + 生成推送正文
python daily_push.py --no-publish  # 只重建本地，不碰线上
python daily_push.py --body-only   # 只生成正文（用现有 payload）
```

邮件正文由 `notify.py` 生成，落到 `05-工作台成品/今日推送.md`，同时打印到终端（`=== 邮件正文开始 ===` 之间）。

## 一条命令

```bash
cd "C:\Users\13024\Desktop\05_芽课项目\芽课项目资料\04-源代码"
python build_workbench.py
```

它会做两件事：先 `ingest.py` 扫一遍 `桌面/素材包` 生成 `payload.json`，再把数据内联进 `template-v2.html`，输出 `05-工作台成品/芽课个人工作库.html`。

只想重建页面、不重扫素材包：

```bash
python build_workbench.py --no-ingest
```

## 数据从哪来

| 层 | 来源 | 更新时机 |
|---|---|---|
| 内容（日记/概念/进度） | `桌面/素材包/**.md` 的 frontmatter 与正文 | 每次跑 build |
| 任务健康（跑没跑） | `ingest.py` 按 12 份排期比对「最后产出日」，`gapDays` = 距最后产出几天 | 每次跑 build |
| 你的复述 / 反驳 / 勾选 / 跳过 | 资料库数据表「芽课·学习痕迹」 | 页面里操作即时写 |

素材包是唯一事实源，`ingest.py` 只读不写。

## 在线版

- 编辑态：https://www.workbuddy.cn/space/d/AlPsT5FPs8TiRhiMeGNtZc
- 分享/手机打开：https://workbuddy.link/p/AlPsT5FPs8TiRhiMeGNtZc
- 数据表：https://www.workbuddy.cn/space/d/YkMcLJUZ8vqF4BrazXmoKd

本地改完 HTML 后要重新上线：

```bash
cd "C:\Program Files\WorkBuddy\resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills\library"
python3 page/import_html.py "<本地html路径>" --node-block-id "AlPsT5FPs8TiRhiMeGNtZc" --databases '[{"id":"YkMcLJUZ8vqF4BrazXmoKd"}]'
python3 page/publish_page.py --node-id "AlPsT5FPs8TiRhiMeGNtZc"
```

链接不变，版本会留。

## 四个视图

| 视图 | 干什么 | 不干什么 |
|---|---|---|
| 今日 | 只给 3 件事：必读 1 期 / 动手 1 个 / 复习 1 概念；顶部红条报断供 | 不列全部 12 领域 |
| 题库 | 28 篇日记 + 46 个概念 + 你写过的反驳，三种模式可搜可筛 | 不做编辑器 |
| 能力剖面 | 193 格热力图 + 四层证据计数 | 不打自评分 |
| 运维 | 12 个任务的最后产出、格数、超期状态 | 不接管调度 |

## 证据怎么记（四层）

| 层 | 怎么产生 | 门槛 |
|---|---|---|
| L0 讲过 | AI 跑出来的日记 | 不计分 |
| L1 复述·反驳 | 阅读弹窗里写复述，或只写一句「我不同意」 | 复述 ≥30 字 / 反驳 ≥10 字 |
| L2 落地 | 勾选今日动手项（≥1 项） | 勾一个就算 |
| L3 用过 | 同一格累计「用上了」≥3 次 | 目前还没有入口 |

「我不同意」在今日页卡片和阅读弹窗里都有，是设计上摩擦最低的入口——30 秒就能留下一条个人语料。

## 数据表字段

「芽课·学习痕迹」四列全文本：`键` / `类型` / `内容` / `时间`。类型取值：

- `digest` 复述、`rebut` 反驳 → 键为 `日期|领域`
- `check` 动手项 → 键为 `日期|领域#序号`，内容为 `1`/`0`
- `read` 标记读完 → 内容为日期
- `verdict` 跳过 → 内容为「跳过」
- `applied` 用过次数 → 内容为数字

## 已知限制

1. **复述和反驳都不写回 md**。存在数据表里，所以 Obsidian 看不到。`ingest.py` 的 L1 统计也不含它，页面里的层级是实时按数据表算的。
2. **离线可用但不同步**。断网时读写走 localStorage，恢复后不会自动补推（`syncPush` 失败只提示「待重试」，没有重试队列）。
3. **任务健康是推断的**。`ingest.py` 只知道「该出没出」，不知道失败原因——真报错了要回 WorkBuddy 的自动任务里看。
4. **导出备份在侧栏底部**，是 JSON 快照，用于换机或迁移，不做自动定时备份。

## 脚本分工

| 脚本 | 干什么 | 会不会写东西 |
|---|---|---|
| `ingest.py` | 扫素材包 → `payload.json` | 只读素材包 |
| `build_workbench.py` | 模板 + payload → 单文件 HTML | 只写 html |
| `notify.py` | payload → 一封短邮件正文 | 写 `今日推送.md` |
| `daily_push.py` | 上面三步 + 导入发布，一条命令 | 会改线上页面 |

## 数据新鲜度

页面是**构建时快照**，不是实时。快照时间在侧栏底部和页脚都有。

这是踩过的坑：11-04 白天健康、计算机已经补跑了，但页面还挂着 11-03 的快照，红条继续报「3 个任务该跑没跑」。**看到的断供状态最多可能旧一天**——自从有了每日 08:30 的自动构建，这个窗口被压到 24 小时内。

## 改样式改哪里

`04-源代码/template-v2.html` 一个文件，CSS 在 `<style>`，逻辑在 `<script>`。改完必须跑 `build_workbench.py` 才会进 `芽课个人工作库.html`——直接改后者会在下次构建时被覆盖。
