package com.genquiz.bk.community;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

public class TopicBookmarkId implements Serializable {
    private UUID userId;
    private UUID topicId;

    public TopicBookmarkId() {}
    public TopicBookmarkId(UUID userId, UUID topicId) { this.userId = userId; this.topicId = topicId; }

    @Override public boolean equals(Object other) {
        return this == other || other instanceof TopicBookmarkId that
                && Objects.equals(userId, that.userId) && Objects.equals(topicId, that.topicId);
    }
    @Override public int hashCode() { return Objects.hash(userId, topicId); }
}

