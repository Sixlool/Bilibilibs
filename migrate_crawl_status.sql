-- 采集进度表（多 worker 共享状态，替代进程内内存字典）
CREATE TABLE IF NOT EXISTS crawl_status (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    running TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否采集运行中',
    job VARCHAR(32) NOT NULL DEFAULT '' COMMENT '任务类型 index/refresh_db/sync_subscribed/detail',
    detail_media_id INT NULL COMMENT '详情刷新目标 media_id',
    page INT NOT NULL DEFAULT 0 COMMENT '当前页',
    pages INT NOT NULL DEFAULT 0 COMMENT '总页数',
    items INT NOT NULL DEFAULT 0 COMMENT '已采集条数',
    message VARCHAR(512) NOT NULL DEFAULT '' COMMENT '状态消息',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采集进度';
