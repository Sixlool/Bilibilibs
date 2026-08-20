-- 为 user 表添加 is_auto_created（扫码自动创建的临时账号）字段，并标记历史 bili_ 前缀账号
ALTER TABLE user ADD COLUMN is_auto_created TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否扫码自动创建的临时账号（未绑定真实账号密码）' AFTER is_admin;

-- 旧版扫码登录会自动创建 bili_<uid> / bili_cookie_* 匿名账号，标记它们为「自动创建」
UPDATE user SET is_auto_created = 1 WHERE username LIKE 'bili\_%' OR username LIKE 'bili\_cookie\_%';
