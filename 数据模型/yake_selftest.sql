/* ============================================================================
   芽课 · 数据模型自测脚本
   ----------------------------------------------------------------------------
   用途：在测试库验证 6.3 状态机的推进与回退是否符合 PRD，不改动任何存量数据。
   前置：先执行 yake_schema_v1.sql（脚本要用到 seed 出来的顶层节点 node_id=6）
   用法：mysql -u<user> -p <db> < yake_selftest.sql
        每条 SELECT 的 result 列为 PASS / FAIL。
   原理：全程在一个事务里造数，最后 ROLLBACK，库里不留痕迹。
   ========================================================================== */

START TRANSACTION;

/* ---------- 造一套最小数据：1 个节点 + 1 文档 + 1 格 + 1 任务 ---------- */
INSERT INTO t_user (role, learn_mode, nickname) VALUES ('learner', 'route', '[自测]用户');
SET @uid = LAST_INSERT_ID();

INSERT INTO t_node (parent_id, level, sort_no, node_name, path)
VALUES (6, 2, 10, '[自测]RAG 检索增强', '/6/');
SET @nid = LAST_INSERT_ID();
UPDATE t_node SET path = CONCAT('/6/', @nid) WHERE node_id = @nid;

INSERT INTO t_doc (title, content) VALUES ('[自测]文档', '原理正文');
SET @did = LAST_INSERT_ID();

INSERT INTO t_card (title, content, published_at) VALUES ('[自测]一格', '一格正文', NOW());
SET @cid = LAST_INSERT_ID();

INSERT INTO t_task (type_tag, question) VALUES ('面试题', '请说明 RAG 的召回与重排分工');
SET @tid = LAST_INSERT_ID();

INSERT INTO t_node_doc  (node_id, doc_id)  VALUES (@nid, @did);
INSERT INTO t_node_card (node_id, card_id) VALUES (@nid, @cid);
INSERT INTO t_node_task (node_id, task_id) VALUES (@nid, @tid);

/* ---------- 1. 初始：未触碰 → grey ---------- */
SELECT '[1] 无任何行为' AS step,
       IF(s.main_state = 'grey' AND s.task_done_flag = 0, 'PASS', 'FAIL') AS result,
       s.main_state, s.task_done_flag
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

/* ---------- 2. 标记文档已读 → blue ---------- */
INSERT INTO t_read_mark (user_id, doc_id) VALUES (@uid, @did);
SELECT '[2] 已读文档' AS step,
       IF(s.main_state = 'blue', 'PASS', 'FAIL') AS result, s.main_state, s.read_cnt
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

/* ---------- 3. 打开关联一格 → orange（优先级高于 blue） ---------- */
INSERT INTO t_card_view (user_id, card_id) VALUES (@uid, @cid);
SELECT '[3] 浏览一格，橙压蓝' AS step,
       IF(s.main_state = 'orange' AND s.read_cnt = 1 AND s.view_cnt = 1, 'PASS', 'FAIL') AS result,
       s.main_state
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

/* ---------- 4. 提交一句话思考 → red，证据数 +1 ---------- */
INSERT INTO t_thought (user_id, card_id, content)
VALUES (@uid, @cid, '召回解决找得到，重排解决排得准，两件事不能混为一谈。');
SELECT '[4] 提交思考，红压橙' AS step,
       IF(s.main_state = 'red' AND s.thought_cnt = 1, 'PASS', 'FAIL') AS result, s.main_state
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

/* ---------- 5. 一格绑定第二个节点：同一条思考同步归集，证据数不重复 ---------- */
INSERT INTO t_node (parent_id, level, sort_no, node_name, path)
VALUES (6, 2, 20, '[自测]Agent 智能体', '/6/');
SET @nid2 = LAST_INSERT_ID();
UPDATE t_node SET path = CONCAT('/6/', @nid2) WHERE node_id = @nid2;
INSERT INTO t_node_card (node_id, card_id) VALUES (@nid2, @cid);

SELECT '[5] 一格绑两节点，两节点皆红' AS step,
       IF((SELECT COUNT(*) FROM v_user_node_state
            WHERE user_id = @uid AND node_id IN (@nid, @nid2) AND main_state = 'red') = 2,
          'PASS', 'FAIL') AS result;

SELECT '[5b] 证据总数仍为 1（按 thought_id 计，不按节点计）' AS step,
       IF((SELECT COUNT(*) FROM t_thought WHERE user_id = @uid AND is_deleted = 0) = 1,
          'PASS', 'FAIL') AS result;

/* ---------- 6. 任务作答保存 → 绿色角标，主色不变 ---------- */
INSERT INTO t_answer (user_id, task_id, content, saved_at)
VALUES (@uid, @tid, '先召回 20 条再重排到 5 条，理由是……', NOW());
SELECT '[6] 作答保存，绿角标独立' AS step,
       IF(s.task_done_flag = 1 AND s.main_state = 'red', 'PASS', 'FAIL') AS result,
       s.main_state, s.task_done_flag
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

/* ---------- 7. 撤销思考（逻辑删除）→ 回退到 orange，证据数扣减 ---------- */
UPDATE t_thought SET is_deleted = 1, deleted_at = NOW()
 WHERE user_id = @uid AND card_id = @cid;
SELECT '[7] 删思考后回退到橙' AS step,
       IF(s.main_state = 'orange' AND s.thought_cnt = 0, 'PASS', 'FAIL') AS result,
       s.main_state, s.thought_cnt
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

SELECT '[7b] 证据数实时扣减为 0' AS step,
       IF((SELECT COUNT(*) FROM t_thought WHERE user_id = @uid AND is_deleted = 0) = 0,
          'PASS', 'FAIL') AS result;

/* ---------- 8. 删除作答 → 绿角标消失 ---------- */
UPDATE t_answer SET is_deleted = 1, deleted_at = NOW() WHERE user_id = @uid AND task_id = @tid;
SELECT '[8] 删作答后角标消失' AS step,
       IF(s.task_done_flag = 0, 'PASS', 'FAIL') AS result, s.task_done_flag
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

/* ---------- 9. 解绑一格 → 橙色回退到蓝色 ---------- */
DELETE FROM t_node_card WHERE node_id = @nid AND card_id = @cid;
SELECT '[9] 解绑一格后回退到蓝' AS step,
       IF(s.main_state = 'blue' AND s.view_cnt = 0, 'PASS', 'FAIL') AS result, s.main_state
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

/* ---------- 10. 删除已读 → 回退到灰 ---------- */
DELETE FROM t_read_mark WHERE user_id = @uid AND doc_id = @did;
SELECT '[10] 取消已读后回退到灰' AS step,
       IF(s.main_state = 'grey', 'PASS', 'FAIL') AS result, s.main_state
FROM v_user_node_state s WHERE s.user_id = @uid AND s.node_id = @nid;

/* ---------- 11. 未归类思考：恢复思考后，一格已无任何绑定 ---------- */
UPDATE t_thought SET is_deleted = 0, deleted_at = NULL
 WHERE user_id = @uid AND card_id = @cid;
SELECT '[11] 解绑一格后思考进入未归类' AS step,
       IF((SELECT COUNT(*) FROM t_thought t
            WHERE t.user_id = @uid AND t.is_deleted = 0
              AND NOT EXISTS (SELECT 1 FROM t_node_card nc WHERE nc.card_id = t.card_id)) = 1,
          'PASS', 'FAIL') AS result;

/* 收尾：清空本次造的全部数据，测试库恢复原样 */
ROLLBACK;

SELECT 'ROLLBACK 完成，测试数据已回收' AS done;
