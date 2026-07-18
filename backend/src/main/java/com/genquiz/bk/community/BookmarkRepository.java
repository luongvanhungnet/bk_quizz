package com.genquiz.bk.community;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface BookmarkRepository extends JpaRepository<Bookmark, BookmarkId> {
    Optional<Bookmark> findByUserIdAndQuizId(UUID userId, UUID quizId);
    boolean existsByUserIdAndQuizId(UUID userId, UUID quizId);
    long deleteByUserIdAndQuizId(UUID userId, UUID quizId);
    Page<Bookmark> findByUserIdOrderByCreatedAtDesc(UUID userId, Pageable pageable);
}
