# 芽课 YACLASS

> 每天一格，只认你写下的那一句。

给产品经理的系统化学习工具。六个模块、**193 格**，一天只推一格。四种状态里，只有一种算证据 —— **你亲手写下的那句话**。读完只是变个颜色，做题不算、用过不记。

这是写进规则的取舍，不是没做完。

---

## 线上地址

<https://yake-learning-map.app.workbuddy.host/?sharecode=YACEN34NZV>

托管在 WorkBuddy 应用托管（永久链接，无 token 过期）。首次访问带 `?sharecode=` 建立会话 Cookie，之后同源的 `data.js` / `docs.js` 等静态资源正常加载；裸域名不带 sharecode 会返回 403，属正常访问控制。

> 早期曾用 EdgeOne Pages 预览域名（带 `eo_token`，数小时过期），已弃用。

| 页面 | 说明 |
| --- | --- |
| `index.html` | 官网首页：证据模型、六模块地图、试一格交互、订阅 |
| `doc.html?k=m0n0` | 知识点正文页，`k` 为知识点 id，支持直达与前后篇 |
| `bench.html` | 工作台演示（深色）：今日 / 题库 / 能力剖面 / 运维 |
| `privacy.html` | 隐私政策 |

---

## 目录结构

```
.
├── 官网/                      # 全部站点源文件（纯静态，无构建）
│   ├── index.html             # 首页，约 115 KB
│   ├── doc.html               # 知识点正文页
│   ├── bench.html             # 工作台演示
│   ├── privacy.html
│   ├── data.js                # ★ 单一数据真源：6 模块 193 格
│   ├── docs.js                # ★ 26 篇知识点正文（约 2 万字）
│   ├── og.png                 # 社交分享卡 1200×630
│   ├── _make_og.py            # og.png 生成脚本
│   ├── robots.txt / sitemap.xml
│   ├── _pub/                  # 发布副本（.gitignore，发布时生成）
│   └── _bak/                  # 验证截图（.gitignore）
├── 数据模型/                   # PostgreSQL 数据模型
│   ├── yake_schema_v1.sql
│   ├── yake_selftest.sql
│   └── 数据模型说明.md
├── 芽课项目资料/               # 早期阶段归档包（报告 / 质检数据 / 旧版成品）
└── PRD_V1.1_对齐说明.md        # V1.1 口径决策记录
```

## 本地预览

纯静态站点，没有任何依赖和构建步骤，起一个静态服务器即可（`file://` 直接打开会因为 `fetch`/模块策略不一致而出问题）：

```bash
cd 官网
python -m http.server 8080
# 打开 http://localhost:8080/index.html
```

---

## 数据契约

改数据只有一个入口：`官网/data.js`。改完，模块小计 → 总计 → 页脚数字 → 数字条 → 领域胶囊 → 题库 → 热力格 → 文档侧栏全部同步，不需要改第二处。

**知识点 id 规则**：`m<模块序号>n<知识点序号>`，如 `m5n1`（第 6 模块第 2 格）。`data.js` 里由 `MODULES` 汇出 `NODES` / `NODE_BY_ID` / `TOTAL_GRIDS`（193）/ `TOTAL_READ`（36）。

**浏览器端存储**（无后端，全部落 localStorage）：

| 键 | 内容 |
| --- | --- |
| `yc_notes_v1` | 证据。`{格id: [{t, mode, ts, src}]}`，`src==='home'` 标记来自首页「试一格」 |
| `yc_proof_v3` | 首页两步状态，按格隔离：`{by: {格id: {items, plan}}}` |

旧键 `yc_proof_v2`（单格状态）与 `yc_proof`（纯数组）在读取时自动迁移到默认格，仅当真读到旧数据才固化，避免用空壳覆盖。

**三种写入语义**：`evAdd` 按文本去重追加、`evReplace` 定位 `src==='home'` 的条目原地替换（条数不变）、`evClear` 只清当前格且 `src==='home'` 的条目 —— 不碰正文页写的证据。

**节选派生**：`snippetOf(id)` 从 `docs.js` 正文实时派生（`lede` 前两段 + 首个有内容的 `sec` 首段，上限 3 段）。26 格零维护，不另写文案，避免节选与正文对不上。

**动作按格手写**：`TRY_ACTS` 是 26×3 的手写表。原先是写死给默认格的三条，换一格就成了胡话。

---

## 发布

```bash
cd 官网
rm -rf _pub && mkdir -p _pub
cp index.html doc.html bench.html data.js docs.js privacy.html og.png robots.txt sitemap.xml _pub/
```

然后用「应用发布」把 `_pub/` 目录发布上线（会沿用已有的分享链接，内容原地覆盖）。

若将来换域名，一条命令全局替换（`index.html` 头部注释里也留了同一段可复制命令）：

```bash
cd 官网 && python -c "import io;[io.open(f,'w',encoding='utf-8').write(io.open(f,encoding='utf-8').read().replace('yake-learning-map.app.workbuddy.host','你的域名')) for f in ['index.html','doc.html','bench.html','privacy.html','robots.txt','sitemap.xml']]"
```

另需把脚本里的 `CONTACT_EMAIL` 换成品牌邮箱。

---

## 待办

- [ ] **绑定自定义域名** —— 目前是预览域名 + 会过期的 token，分享出去不可用
- [ ] `CONTACT_EMAIL` 仍是 QQ 邮箱，待换品牌邮箱
- [ ] Google Fonts 仍为外链（国内可能慢），中文子集体积大，暂未自托管
- [ ] 三件待产品拍板：橙色态「取消打开记录」入口、`t_answer` 是否留版本历史、删文档是否连带清 `t_read_mark`

---

## 版权

内容与设计归作者所有，未经许可请勿转载或商用。
