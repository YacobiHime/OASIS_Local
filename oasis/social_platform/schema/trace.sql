CREATE TABLE trace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    created_at DATETIME,
    action TEXT,
    info TEXT,
    status TEXT DEFAULT 'success',  -- 追加: 実行の状態 (success または error)
    error_message TEXT,             -- 追加: 不具合発生時の詳細
    FOREIGN KEY(user_id) REFERENCES user(user_id)
);