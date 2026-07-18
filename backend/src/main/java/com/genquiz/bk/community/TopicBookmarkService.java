package com.genquiz.bk.community;

import com.genquiz.bk.explore.ExploreDtos;
import com.genquiz.bk.explore.ExploreService;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TopicBookmarkService {
    private final TopicBookmarkRepository bookmarks;
    private final ExploreService explore;

    public TopicBookmarkService(TopicBookmarkRepository bookmarks, ExploreService explore) {
        this.bookmarks = bookmarks; this.explore = explore;
    }

    @Transactional
    public ExploreDtos.SavedTopic bookmark(UUID userId, UUID topicId) {
        var topic = explore.requirePublic(topicId);
        TopicBookmark bookmark = bookmarks.findByUserIdAndTopicId(userId, topicId)
                .orElseGet(() -> bookmarks.save(new TopicBookmark(userId, topicId, Instant.now())));
        return new ExploreDtos.SavedTopic(explore.summary(topic), bookmark.getCreatedAt());
    }

    @Transactional
    public void unbookmark(UUID userId, UUID topicId) { bookmarks.deleteByUserIdAndTopicId(userId, topicId); }

    @Transactional(readOnly = true)
    public Page<ExploreDtos.SavedTopic> list(UUID userId, int page, int limit) {
        return bookmarks.findByUserIdOrderByCreatedAtDesc(userId, PageRequest.of(page - 1, limit))
                .map(bookmark -> new ExploreDtos.SavedTopic(
                        explore.summary(explore.requirePublic(bookmark.getTopicId())), bookmark.getCreatedAt()));
    }
}
