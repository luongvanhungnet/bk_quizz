package com.genquiz.bk.community;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TopicBookmarkRepository extends JpaRepository<TopicBookmark, TopicBookmarkId> {
    Optional<TopicBookmark> findByUserIdAndTopicId(UUID userId, UUID topicId);
    long deleteByUserIdAndTopicId(UUID userId, UUID topicId);
    Page<TopicBookmark> findByUserIdOrderByCreatedAtDesc(UUID userId, Pageable pageable);
    long countByTopicId(UUID topicId);
}
