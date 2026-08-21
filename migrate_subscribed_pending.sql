-- 追番待同步队列：用户查看「我的追番」时，未入库的追番加入此队列，管理员统一同步入库
CREATE TABLE IF NOT EXISTS subscribed_pending (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL COMMENT '提交该追番的用户',
    media_id INT NULL COMMENT 'B站番剧 media_id',
    season_id INT NULL COMMENT 'B站番剧 season_id',
    title VARCHAR(256) NOT NULL DEFAULT '' COMMENT '番剧标题',
    cover VARCHAR(512) NOT NULL DEFAULT '' COMMENT '封面',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '0=待同步 1=同步中 2=已同步 3=失败',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_status (status),
    KEY idx_media (media_id),
    KEY idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='追番待同步队列';
