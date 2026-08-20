-- 为 user 表添加管理员标记字段（已有库执行本迁移；新库直接用 init_db.sql）
ALTER TABLE user ADD COLUMN is_admin TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否管理员（1=可进入后台管理）' AFTER bilibili_bili_jct;

-- 可选：直接指定某用户为管理员（把 'your_admin_username' 换成实际用户名后执行）
-- UPDATE user SET is_admin = 1 WHERE username = 'your_admin_username';
