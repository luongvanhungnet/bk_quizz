CREATE TABLE topic_bookmarks (
    user_id UUID NOT NULL,
    topic_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_topic_bookmarks PRIMARY KEY (user_id, topic_id),
    CONSTRAINT fk_topic_bookmarks_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_topic_bookmarks_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

CREATE INDEX idx_topic_bookmarks_topic_created
    ON topic_bookmarks (topic_id, created_at DESC);

