-- B站动漫番剧数据分析系统 - 数据库初始化脚本
-- 使用前请先创建数据库：CREATE DATABASE IF NOT EXISTS bilibili_bangumi DEFAULT CHARSET utf8mb4;
-- 执行方式：mysql -u root -p123456 < init_db.sql 或在 MySQL 客户端中执行

USE bilibili_bangumi;

-- 番剧季度/索引维度表（如 2024年1月番）
CREATE TABLE IF NOT EXISTS bangumi_season (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    year SMALLINT UNSIGNED NOT NULL COMMENT '年份',
    season TINYINT UNSIGNED NOT NULL COMMENT '季度: 1冬 4春 7夏 10秋',
    label VARCHAR(32) NOT NULL DEFAULT '' COMMENT '季度标签 如 2024年1月番',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_year_season (year, season)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='番剧季度表';

-- 番剧基本信息表
CREATE TABLE IF NOT EXISTS bangumi_info (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    media_id INT UNSIGNED NOT NULL COMMENT '番剧 media_id',
    season_id INT UNSIGNED NOT NULL COMMENT '季度 season_id',
    title VARCHAR(256) NOT NULL DEFAULT '' COMMENT '标题',
    cover VARCHAR(512) NOT NULL DEFAULT '' COMMENT '封面URL',
    intro TEXT COMMENT '简介',
    pub_time DATETIME NULL COMMENT '开播/发布时间',
    score DECIMAL(3,2) NULL COMMENT '评分',
    score_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '评分人数',
    follow_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '追番数',
    play_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '播放量',
    danmaku_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '弹幕总数',
    coin_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '投币数',
    fav_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '收藏数',
    series_count SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '总集数',
    area VARCHAR(64) NOT NULL DEFAULT '' COMMENT '地区',
    season_type TINYINT NOT NULL DEFAULT 1 COMMENT '类型 1番剧 3影视 4国创',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_media_id (media_id),
    KEY idx_season_id (season_id),
    KEY idx_pub_time (pub_time),
    KEY idx_score (score),
    KEY idx_play_count (play_count),
    KEY idx_follow_count (follow_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='番剧基本信息表';

-- 番剧分集表
CREATE TABLE IF NOT EXISTS bangumi_episode (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    season_id INT UNSIGNED NOT NULL COMMENT 'season_id',
    episode_id INT UNSIGNED NOT NULL COMMENT '单集 ep_id',
    index_title VARCHAR(128) NOT NULL DEFAULT '' COMMENT '集标题',
    long_title VARCHAR(512) NOT NULL DEFAULT '' COMMENT '长标题',
    duration INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '时长秒',
    pub_time DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_season_ep (season_id, episode_id),
    KEY idx_season_id (season_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='番剧分集表';

-- 番剧每日统计快照表（用于趋势回溯）
CREATE TABLE IF NOT EXISTS bangumi_daily_snapshot (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    media_id INT UNSIGNED NOT NULL,
    snapshot_date DATE NOT NULL COMMENT '快照日期',
    play_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    follow_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    danmaku_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    coin_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    fav_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    score DECIMAL(3,2) NULL,
    score_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_media_date (media_id, snapshot_date),
    KEY idx_snapshot_date (snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='番剧每日统计快照';

-- 标签表
CREATE TABLE IF NOT EXISTS tag_info (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tag_name VARCHAR(64) NOT NULL COMMENT '标签名',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tag_name (tag_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标签表';

-- 番剧-标签关联表
CREATE TABLE IF NOT EXISTS bangumi_tag (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    media_id INT UNSIGNED NOT NULL,
    tag_id INT UNSIGNED NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_media_tag (media_id, tag_id),
    KEY idx_tag_id (tag_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='番剧标签关联';

-- 用户表（个人中心、收藏）
CREATE TABLE IF NOT EXISTS user (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL COMMENT '用户名',
    password_hash VARCHAR(256) NOT NULL COMMENT '密码哈希',
    email VARCHAR(128) NOT NULL DEFAULT '',
    bilibili_uid BIGINT NULL COMMENT 'B站用户mid，扫码登录时关联',
    bilibili_sessdata VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'B站Cookie sessdata，采集时带登录态降低412',
    bilibili_bili_jct VARCHAR(256) NOT NULL DEFAULT '' COMMENT 'B站Cookie bili_jct',
    is_admin TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否管理员（1=可进入后台管理）',
    is_auto_created TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否扫码自动创建的临时账号（未绑定真实账号密码）',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_username (username),
    UNIQUE KEY uk_bilibili_uid (bilibili_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- 用户收藏番剧表
CREATE TABLE IF NOT EXISTS user_favorite (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    media_id INT UNSIGNED NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_media (user_id, media_id),
    KEY idx_user_id (user_id),
    KEY idx_media_id (media_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户收藏番剧';
