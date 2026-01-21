-- 创建数据库表
CREATE TABLE media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT CHECK(type IN ('video', 'image', 'text')),
    path TEXT NOT NULL,
    duration INTEGER,  -- 图片/文字显示时长（秒）
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_size INTEGER
);

CREATE TABLE schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    play_duration INTEGER,  -- 覆盖media中的duration
    priority INTEGER DEFAULT 0,
    is_temporary BOOLEAN DEFAULT 0,
    played_count INTEGER DEFAULT 0,
    FOREIGN KEY (media_id) REFERENCES media(id)
);

CREATE TABLE screen_config (
    id INTEGER PRIMARY KEY,
    screen_width INTEGER DEFAULT 1920,
    screen_height INTEGER DEFAULT 1080,
    refresh_rate INTEGER DEFAULT 60,
    brightness INTEGER DEFAULT 100,
    volume INTEGER DEFAULT 50,
    schedule_window_enabled INTEGER DEFAULT 0,
    schedule_window_start TEXT,
    schedule_window_end TEXT
);
