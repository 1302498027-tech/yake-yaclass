/* ============================================================================
   芽课 · 学习地图 / 知识库模块  数据模型 DDL
   ----------------------------------------------------------------------------
   依据：芽课-学习地图与知识库模块PRD-V1.1（2026-11-06）
         6.2 证据认定 / 6.2.1 归集映射 / 6.3 节点状态机 / 6.4 数据模型
         6.4.1 字段级数据字典 / FR-03 / FR-06 / FR-07

   目标库：MySQL 8.0.16+（CHECK 约束需 8.0.16；ngram 分词为内置插件）
   字符集：utf8mb4 / utf8mb4_0900_ai_ci（若为 5.7 见文末「兼容性说明」）

   与 PRD 的差异（每一处都写在后面 SCHEMA-NOTES.md 里，此处只列结论）
     1. 内容表统一补 is_deleted + deleted_at        → FR-07「逻辑删除 30 天」
     2. t_thought 补 updated_at                     → FR-03-3「编辑记录最后更新时间」
     3. t_answer 补 created_at / saved_at / 草稿字段 → FR-03-4「30 秒自动存草稿」
     4. 新增 t_card_view                            → 6.3 橙色态在 PRD 模型里没有数据源
     5. 新增 t_audit_log                            → FR-07「审计日志保留 180 天」
     6. 新增 t_export_job                           → FR-06 异步导出没有落地与通知载体
     7. t_user.role 去掉 tourist                    → 游客未登录，不产生用户行
     8. 正文加 FULLTEXT(ngram) 索引                  → FR-04「搜索 ≤ 1 秒」

   执行顺序有依赖，勿打乱；全部为 IF NOT EXISTS，可重复执行。
   ========================================================================== */

SET NAMES utf8mb4;

/* ----------------------------------------------------------------------------
   一、实体表（8 张，PRD 6.4）
   -------------------------------------------------------------------------- */

/* 1. 用户 -------------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS t_user (
  user_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户唯一标识',
  role        VARCHAR(16)  NOT NULL DEFAULT 'learner'
              COMMENT 'learner=学习者 / ops=内容运营管理员 / admin=超级管理员。游客不入库',
  learn_mode  VARCHAR(16)  NULL DEFAULT NULL
              COMMENT 'free=随缘模式（默认） / route=体系路线模式；对账号持久化',
  nickname    VARCHAR(64)  NULL DEFAULT NULL COMMENT '昵称',
  status      TINYINT      NOT NULL DEFAULT 1 COMMENT '1=正常 0=停用（不物理删除）',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id),
  KEY idx_user_role (role),
  CONSTRAINT ck_user_role CHECK (role IN ('learner','ops','admin')),
  CONSTRAINT ck_user_mode CHECK (learn_mode IS NULL OR learn_mode IN ('free','route'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户（角色见 5.1）';

/* 2. 知识树节点 -------------------------------------------------------- */
/* parent_id 自关联；顶层 6 模块固定，二级及以下可无限添加（FR-02） */
CREATE TABLE IF NOT EXISTS t_node (
  node_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '节点唯一标识',
  parent_id  BIGINT UNSIGNED NULL COMMENT '父节点；顶层为 NULL',
  level      TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '层级深度，顶层=1',
  sort_no    INT          NOT NULL DEFAULT 0 COMMENT '同级排序，升序',
  node_name  VARCHAR(128) NOT NULL COMMENT '节点名称',
  path       VARCHAR(512) NOT NULL DEFAULT ''
             COMMENT '物化路径 /1/12/125：面包屑、子树查询、导出三级结构都用它',
  is_deleted TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除（FR-07）',
  deleted_at DATETIME     NULL DEFAULT NULL,
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (node_id),
  KEY idx_node_parent (parent_id, sort_no),
  KEY idx_node_path (path),
  KEY idx_node_alive (is_deleted, parent_id),
  CONSTRAINT fk_node_parent FOREIGN KEY (parent_id) REFERENCES t_node (node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='知识树节点';

/* 3. 知识库文档 -------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS t_doc (
  doc_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '文档唯一标识',
  title      VARCHAR(255) NOT NULL COMMENT '文档标题',
  content    LONGTEXT     NOT NULL COMMENT 'Markdown 正文（XSS 净化在应用层，渲染前过滤）',
  content_hash CHAR(64)   NULL DEFAULT NULL COMMENT '正文 SHA-256，用于缓存与导出增量',
  is_deleted TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除，回收站 30 天',
  deleted_at DATETIME     NULL DEFAULT NULL,
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (doc_id),
  KEY idx_doc_alive (is_deleted, updated_at),
  FULLTEXT KEY ft_doc (title, content) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='知识库文档（Markdown）';

/* 4. 一格 -------------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS t_card (
  card_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '一格唯一标识',
  title        VARCHAR(255) NOT NULL COMMENT '一格标题',
  content      LONGTEXT     NOT NULL COMMENT '一格正文',
  published_at DATETIME     NULL DEFAULT NULL COMMENT '发布时间；Tab 二按此倒序',
  is_deleted   TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除；删除后历史思考转未归类',
  deleted_at   DATETIME     NULL DEFAULT NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (card_id),
  KEY idx_card_pub (is_deleted, published_at),
  FULLTEXT KEY ft_card (title, content) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='每日一格';

/* 5. 一句话思考（唯一有效学习证据） ------------------------------------ */
CREATE TABLE IF NOT EXISTS t_thought (
  thought_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '思考唯一标识',
  user_id      BIGINT UNSIGNED NOT NULL COMMENT '提交人',
  card_id      BIGINT UNSIGNED NOT NULL COMMENT '来源一格（归属节点由绑定关系派生，不落库）',
  content      VARCHAR(200)    NOT NULL COMMENT '5–200 字；前后端双重校验',
  is_deleted   TINYINT         NOT NULL DEFAULT 0 COMMENT '逻辑删除；删除后证据数实时扣减',
  deleted_at   DATETIME        NULL DEFAULT NULL,
  submitted_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '提交时间',
  updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
               COMMENT '最后编辑时间（PRD V1.1 原文要求记录，字典漏字段）',
  PRIMARY KEY (thought_id),
  KEY idx_thought_user (user_id, is_deleted, submitted_at),
  KEY idx_thought_card (card_id, is_deleted),
  FULLTEXT KEY ft_thought (content) WITH PARSER ngram,
  CONSTRAINT fk_thought_user FOREIGN KEY (user_id) REFERENCES t_user (user_id),
  CONSTRAINT fk_thought_card FOREIGN KEY (card_id) REFERENCES t_card (card_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='一句话思考（唯一有效证据）';

/* 6. 配套任务 ---------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS t_task (
  task_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '任务唯一标识',
  type_tag   VARCHAR(32)  NULL DEFAULT NULL COMMENT '面试题 / 实操任务 / 章节练习 / 案例拆解',
  question   LONGTEXT     NOT NULL COMMENT 'Markdown 题干（本期全部主观题）',
  is_deleted TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除，任务停用',
  deleted_at DATETIME     NULL DEFAULT NULL,
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (task_id),
  KEY idx_task_type (type_tag, is_deleted),
  FULLTEXT KEY ft_task (question) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='配套任务与面试题';

/* 7. 任务作答 ---------------------------------------------------------- */
/* 一人一题一行：正式作答与草稿同库存放，避免草稿表与正式表两处漂移 */
CREATE TABLE IF NOT EXISTS t_answer (
  answer_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '作答唯一标识',
  user_id       BIGINT UNSIGNED NOT NULL COMMENT '作答人',
  task_id       BIGINT UNSIGNED NOT NULL COMMENT '所属任务',
  content       LONGTEXT  NULL DEFAULT NULL COMMENT '正式作答（点保存后写入）',
  draft_content LONGTEXT  NULL DEFAULT NULL COMMENT '草稿正文（每 30 秒自动覆盖）',
  draft_saved_at DATETIME NULL DEFAULT NULL COMMENT '草稿最后保存时间，用于前端提示"已自动保存"',
  saved_at      DATETIME  NULL DEFAULT NULL COMMENT '首次保存时间；非空才算"已完成任务"',
  is_deleted    TINYINT   NOT NULL DEFAULT 0 COMMENT '逻辑删除；删除后绿色角标重算',
  deleted_at    DATETIME  NULL DEFAULT NULL,
  created_at    DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次落库（打草稿也算）',
  updated_at    DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (answer_id),
  UNIQUE KEY uk_answer_user_task (user_id, task_id),
  KEY idx_answer_task (task_id, is_deleted, saved_at),
  CONSTRAINT fk_answer_user FOREIGN KEY (user_id) REFERENCES t_user (user_id),
  CONSTRAINT fk_answer_task FOREIGN KEY (task_id) REFERENCES t_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='任务作答（含草稿）';

/* 8. 已读记录（文档级全局状态，跨节点只计一次） ----------------------- */
CREATE TABLE IF NOT EXISTS t_read_mark (
  user_id   BIGINT UNSIGNED NOT NULL COMMENT '用户',
  doc_id    BIGINT UNSIGNED NOT NULL COMMENT '文档',
  marked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '标记时间',
  PRIMARY KEY (user_id, doc_id),
  KEY idx_read_doc (doc_id, user_id),
  CONSTRAINT fk_read_user FOREIGN KEY (user_id) REFERENCES t_user (user_id),
  CONSTRAINT fk_read_doc  FOREIGN KEY (doc_id)  REFERENCES t_doc (doc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='文档已读（取消已读=删行，属状态不属内容，不参与逻辑删除）';

/* ----------------------------------------------------------------------------
   二、必备补充：PRD 6.3 的"橙色态"在 6.4 里没有数据源
   橙色 = 打开过节点绑定的任一格。埋点 card_view 只是事件流，
   不能作为状态回退（"解绑后无打开记录"）的判定依据，所以必须落表。
   -------------------------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS t_card_view (
  user_id         BIGINT UNSIGNED NOT NULL COMMENT '用户',
  card_id         BIGINT UNSIGNED NOT NULL COMMENT '一格',
  first_viewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次打开',
  last_viewed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最近打开',
  view_count      INT      NOT NULL DEFAULT 1 COMMENT '打开次数',
  PRIMARY KEY (user_id, card_id),
  KEY idx_view_card (card_id, user_id),
  CONSTRAINT fk_view_user FOREIGN KEY (user_id) REFERENCES t_user (user_id),
  CONSTRAINT fk_view_card FOREIGN KEY (card_id) REFERENCES t_card (card_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='一格打开记录（支撑节点橙色态）';

/* ----------------------------------------------------------------------------
   三、多对多绑定表（3 张，PRD 6.4.1）
   绑定关系用物理删除：它是"关系"不是"内容"，逻辑删除会让唯一键
   (node_id, doc_id) 与重新绑定冲突；解绑动作由 t_audit_log 留痕。
   -------------------------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS t_node_doc (
  node_id  BIGINT UNSIGNED NOT NULL COMMENT '节点',
  doc_id   BIGINT UNSIGNED NOT NULL COMMENT '文档（一篇文档可挂多个节点）',
  bind_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '绑定时间',
  bound_by BIGINT UNSIGNED NULL COMMENT '操作人，便于追责',
  PRIMARY KEY (node_id, doc_id),
  KEY idx_nd_doc (doc_id, node_id),
  CONSTRAINT fk_nd_node FOREIGN KEY (node_id) REFERENCES t_node (node_id),
  CONSTRAINT fk_nd_doc  FOREIGN KEY (doc_id)  REFERENCES t_doc (doc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='节点-文档绑定';

CREATE TABLE IF NOT EXISTS t_node_card (
  node_id  BIGINT UNSIGNED NOT NULL COMMENT '节点',
  card_id  BIGINT UNSIGNED NOT NULL COMMENT '一格（一格可绑多个节点，思考按此归集）',
  bind_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '绑定时间',
  bound_by BIGINT UNSIGNED NULL COMMENT '操作人',
  PRIMARY KEY (node_id, card_id),
  KEY idx_nc_card (card_id, node_id),
  CONSTRAINT fk_nc_node FOREIGN KEY (node_id) REFERENCES t_node (node_id),
  CONSTRAINT fk_nc_card FOREIGN KEY (card_id) REFERENCES t_card (card_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='节点-一格绑定';

CREATE TABLE IF NOT EXISTS t_node_task (
  node_id  BIGINT UNSIGNED NOT NULL COMMENT '节点',
  task_id  BIGINT UNSIGNED NOT NULL COMMENT '任务',
  bind_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '绑定时间',
  bound_by BIGINT UNSIGNED NULL COMMENT '操作人',
  PRIMARY KEY (node_id, task_id),
  KEY idx_nt_task (task_id, node_id),
  CONSTRAINT fk_nt_node FOREIGN KEY (node_id) REFERENCES t_node (node_id),
  CONSTRAINT fk_nt_task FOREIGN KEY (task_id) REFERENCES t_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='节点-任务绑定';

/* ----------------------------------------------------------------------------
   四、后台支撑表（FR-07 / FR-06）
   -------------------------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS t_audit_log (
  log_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  operator_id BIGINT UNSIGNED NULL COMMENT '操作人；系统任务为 NULL',
  action      VARCHAR(32)  NOT NULL COMMENT 'create/update/delete/restore/bind/unbind',
  object_type VARCHAR(32)  NOT NULL COMMENT 'node/doc/card/task/binding/user',
  object_id   BIGINT UNSIGNED NOT NULL COMMENT '对象 ID',
  before_state JSON NULL COMMENT '变更前快照',
  after_state  JSON NULL COMMENT '变更后快照',
  ip          VARCHAR(45) NULL COMMENT '操作来源 IP（v6 最长 45）',
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (log_id),
  KEY idx_audit_obj (object_type, object_id, created_at),
  KEY idx_audit_op (operator_id, created_at),
  CONSTRAINT fk_audit_user FOREIGN KEY (operator_id) REFERENCES t_user (user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='后台操作审计（保留 180 天，按 created_at 归档清理）';

CREATE TABLE IF NOT EXISTS t_export_job (
  job_id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id       BIGINT UNSIGNED NOT NULL COMMENT '导出发起人',
  status        VARCHAR(16) NOT NULL DEFAULT 'pending'
                COMMENT 'pending/running/done/failed/expired',
  thought_cnt   INT NOT NULL DEFAULT 0 COMMENT '导出思考条数',
  answer_cnt    INT NOT NULL DEFAULT 0 COMMENT '导出作答条数',
  file_path     VARCHAR(512) NULL DEFAULT NULL COMMENT '产物路径或对象存储 key',
  error_msg     VARCHAR(255) NULL DEFAULT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at   DATETIME NULL DEFAULT NULL,
  expires_at    DATETIME NULL DEFAULT NULL COMMENT '产物过期时间，建议 7 天',
  PRIMARY KEY (job_id),
  KEY idx_job_user (user_id, created_at),
  KEY idx_job_status (status, created_at),
  CONSTRAINT fk_job_user FOREIGN KEY (user_id) REFERENCES t_user (user_id),
  CONSTRAINT ck_job_status CHECK (status IN ('pending','running','done','failed','expired'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学习证据异步导出任务';

/* ----------------------------------------------------------------------------
   五、视图：把 6.3 状态机直接算出来
   v_user_node_status 给出四个计数，v_user_node_state 给出主色与角标。
   主色优先级 红 > 橙 > 浅蓝 > 灰（6.3），绿色角标独立于主色。
   -------------------------------------------------------------------------- */
CREATE OR REPLACE ALGORITHM=MERGE VIEW v_user_node_status AS
SELECT
  u.user_id,
  n.node_id,
  (SELECT COUNT(*)
     FROM t_node_card nc
     JOIN t_thought t ON t.card_id = nc.card_id
                     AND t.user_id = u.user_id
                     AND t.is_deleted = 0
    WHERE nc.node_id = n.node_id)                       AS thought_cnt,
  (SELECT COUNT(*)
     FROM t_node_doc nd
     JOIN t_read_mark rm ON rm.doc_id = nd.doc_id
                        AND rm.user_id = u.user_id
    WHERE nd.node_id = n.node_id)                       AS read_cnt,
  (SELECT COUNT(*)
     FROM t_node_card nc
     JOIN t_card_view cv ON cv.card_id = nc.card_id
                        AND cv.user_id = u.user_id
    WHERE nc.node_id = n.node_id)                       AS view_cnt,
  (SELECT COUNT(*)
     FROM t_node_task nt
     JOIN t_answer a ON a.task_id = nt.task_id
                    AND a.user_id = u.user_id
                    AND a.is_deleted = 0
                    AND a.saved_at IS NOT NULL
    WHERE nt.node_id = n.node_id)                       AS answer_cnt
FROM t_user u
CROSS JOIN t_node n
WHERE n.is_deleted = 0;

CREATE OR REPLACE ALGORITHM=MERGE VIEW v_user_node_state AS
SELECT
  s.user_id,
  s.node_id,
  s.thought_cnt,
  s.read_cnt,
  s.view_cnt,
  s.answer_cnt,
  CASE
    WHEN s.thought_cnt > 0 THEN 'red'      /* 已提交思考：核心状态 */
    WHEN s.view_cnt    > 0 THEN 'orange'   /* 浏览过关联一格 */
    WHEN s.read_cnt    > 0 THEN 'blue'     /* 已读知识库文档 */
    ELSE 'grey'                            /* 未触碰 */
  END AS main_state,
  (s.answer_cnt > 0) AS task_done_flag     /* 绿色角标 */
FROM v_user_node_status s;

/* ----------------------------------------------------------------------------
   六、初始数据：六大顶层模块（FR-02 固定，sort_no 留间隔便于插入）
   -------------------------------------------------------------------------- */
INSERT INTO t_node (node_id, parent_id, level, sort_no, node_name, path) VALUES
  (1, NULL, 1, 10, '产品认知基础', '/1'),
  (2, NULL, 1, 20, '需求分析',     '/2'),
  (3, NULL, 1, 30, '产品设计',     '/3'),
  (4, NULL, 1, 40, '项目管理',     '/4'),
  (5, NULL, 1, 50, '数据分析',     '/5'),
  (6, NULL, 1, 60, 'AI 产品实战',  '/6')
ON DUPLICATE KEY UPDATE node_name = VALUES(node_name), sort_no = VALUES(sort_no);

/* ----------------------------------------------------------------------------
   七、常用查询（照抄可用，把 :uid 换成实际用户 ID）
   -------------------------------------------------------------------------- */

/* 7.1 地图顶部三张统计卡（FR-02） */
-- 有效证据总数：按思考唯一 ID 计数，与挂载节点数无关
-- SELECT COUNT(*) FROM t_thought WHERE user_id = :uid AND is_deleted = 0;
-- 已读文档数：去重文档，跨节点只计一次
-- SELECT COUNT(DISTINCT doc_id) FROM t_read_mark WHERE user_id = :uid;
-- 已完成任务数：有作答保存记录的任务
-- SELECT COUNT(DISTINCT task_id) FROM t_answer
--  WHERE user_id = :uid AND is_deleted = 0 AND saved_at IS NOT NULL;

/* 7.2 未归类思考（一格未绑定节点，或绑定后被解绑/删除） */
-- SELECT t.thought_id, t.content, t.submitted_at
--   FROM t_thought t
--  WHERE t.user_id = :uid AND t.is_deleted = 0
--    AND NOT EXISTS (
--      SELECT 1 FROM t_node_card nc
--        JOIN t_node n ON n.node_id = nc.node_id AND n.is_deleted = 0
--       WHERE nc.card_id = t.card_id
--    )
--  ORDER BY t.submitted_at DESC;

/* 7.3 单个节点的四计数与主色 */
-- SELECT main_state, task_done_flag, thought_cnt, read_cnt, view_cnt, answer_cnt
--   FROM v_user_node_state WHERE user_id = :uid AND node_id = :nid;

/* 7.4 某个节点的 Tab 三：我的思考（经绑定关系归集，同一思考可出现在多个节点） */
-- SELECT t.thought_id, t.content, t.submitted_at, t.updated_at
--   FROM t_node_card nc
--   JOIN t_thought t ON t.card_id = nc.card_id
--  WHERE nc.node_id = :nid AND t.user_id = :uid AND t.is_deleted = 0
--  ORDER BY t.submitted_at DESC;

/* 7.5 导出用：按 模块 → 知识点 → 思考/作答 → 时间 三级结构取数（FR-06） */
-- SELECT n.node_id, n.path, n.node_name, 'thought' AS kind,
--        t.content, t.submitted_at AS at
--   FROM t_node n
--   LEFT JOIN t_node_card nc ON nc.node_id = n.node_id
--   LEFT JOIN t_thought t    ON t.card_id = nc.card_id AND t.user_id = :uid AND t.is_deleted = 0
--  WHERE n.is_deleted = 0 AND t.thought_id IS NOT NULL
-- UNION ALL
-- SELECT n.node_id, n.path, n.node_name, 'answer', a.content, a.saved_at
--   FROM t_node n
--   LEFT JOIN t_node_task nt ON nt.node_id = n.node_id
--   LEFT JOIN t_answer a     ON a.task_id = nt.task_id AND a.user_id = :uid
--                           AND a.is_deleted = 0 AND a.saved_at IS NOT NULL
--  WHERE n.is_deleted = 0 AND a.answer_id IS NOT NULL
--  ORDER BY path, at;

/* 7.6 全站搜索（FR-04）：四类内容分组，关键词高亮交给应用层 */
-- SELECT 'doc' AS kind, doc_id AS id, title, NULL AS node_path
--   FROM t_doc WHERE is_deleted = 0 AND MATCH(title, content) AGAINST (:kw IN NATURAL LANGUAGE MODE)
-- UNION ALL
-- SELECT 'thought', thought_id, content, NULL
--   FROM t_thought WHERE user_id = :uid AND is_deleted = 0
--     AND MATCH(content) AGAINST (:kw IN NATURAL LANGUAGE MODE)
-- UNION ALL
-- SELECT 'task', task_id, question, NULL
--   FROM t_task WHERE is_deleted = 0 AND MATCH(question) AGAINST (:kw IN NATURAL LANGUAGE MODE);
/* 注意：MATCH 必须在 WHERE 里出现，且全文索引只对词长 ≥ ngram_token_size
   （默认 2）的中文片段生效；单字搜索请回退 LIKE '%字%' 并限制范围。 */

/* ----------------------------------------------------------------------------
   八、兼容性与运维
   - MySQL 5.7：utf8mb4_0900_ai_ci → utf8mb4_general_ci；
                CHECK 约束会被忽略（不报错，但不生效）；
                ngram 需确认已安装（5.7 自带 ngram plugin，需 INSTALL PLUGIN）。
   - 审计日志清理：DELETE FROM t_audit_log WHERE created_at < NOW() - INTERVAL 180 DAY;
   - 回收站清理：对 is_deleted=1 且 deleted_at < NOW() - INTERVAL 30 DAY 的内容做物理删除，
     删除前确认无级联阻断（t_thought/t_answer 本体保留，只解绑）。
   - 初始化路径：新增子节点后需回写 path = CONCAT(parent.path, '/', node_id)，
     建议放业务层事务内完成，或用触发器 t_node_after_insert 补齐。
   ========================================================================== */
