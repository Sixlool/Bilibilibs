-- 为已有 user 表增加 B 站 Cookie 字段（用于登录后采集时带账号请求，降低 412 风控）
-- 若你是全新安装且已执行过 init_db.sql，需在 user 表定义中加上这两列后重建，或执行本脚本补列。

USE bilibili_bangumi;

-- 若提示列已存在可忽略
ALTER TABLE user ADD COLUMN bilibili_uid BIGINT NULL COMMENT 'B站用户mid' AFTER email;
ALTER TABLE user ADD COLUMN bilibili_sessdata VARCHAR(512) DEFAULT '' COMMENT 'B站Cookie';
ALTER TABLE user ADD COLUMN bilibili_bili_jct VARCHAR(256) DEFAULT '' COMMENT 'B站Cookie';
ALTER TABLE user ADD UNIQUE KEY uk_bilibili_uid (bilibili_uid);
