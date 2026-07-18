package com.genquiz.bk.community;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

public class BookmarkId implements Serializable {
    private UUID userId;
    private UUID quizId;

    public BookmarkId() {}

    public BookmarkId(UUID userId, UUID quizId) {
        this.userId = userId;
        this.quizId = quizId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof BookmarkId that)) return false;
        return Objects.equals(userId, that.userId) && Objects.equals(quizId, that.quizId);
    }

    @Override
    public int hashCode() { return Objects.hash(userId, quizId); }
}
