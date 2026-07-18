package com.genquiz.bk.quiz;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
public interface QuizRepository extends JpaRepository<Quiz, UUID> {
    Optional<Quiz> findByIdAndDeletedAtIsNull(UUID id);
    Page<Quiz> findByOwnerIdAndDeletedAtIsNull(UUID ownerId, Pageable pageable);
    Page<Quiz> findByTopicIdAndDeletedAtIsNull(UUID topicId, Pageable pageable);
    Page<Quiz> findByTopicIdAndOwnerIdAndDeletedAtIsNull(UUID topicId, UUID ownerId, Pageable pageable);
    long countByOwnerIdAndDeletedAtIsNull(UUID ownerId);
    long countByTopicIdAndStatusAndVisibilityAndDeletedAtIsNull(
            UUID topicId, QuizStatus status, com.genquiz.bk.topic.Visibility visibility);
    java.util.List<Quiz> findByTopicIdAndStatusAndVisibilityAndDeletedAtIsNullOrderByPublishedAtDesc(
            UUID topicId, QuizStatus status, com.genquiz.bk.topic.Visibility visibility);
    java.util.List<Quiz> findByTopicIdAndStatusAndVisibilityAndModerationStatusAndDeletedAtIsNullOrderByPublishedAtDesc(
            UUID topicId, QuizStatus status, com.genquiz.bk.topic.Visibility visibility, com.genquiz.bk.common.ModerationStatus moderationStatus);
}
