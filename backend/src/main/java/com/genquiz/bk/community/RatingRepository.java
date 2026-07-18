package com.genquiz.bk.community;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;
import java.util.UUID;

public interface RatingRepository extends JpaRepository<Rating, UUID> {
    Optional<Rating> findByUserIdAndQuizIdAndDeletedAtIsNull(UUID userId, UUID quizId);
    Page<Rating> findByQuizIdAndDeletedAtIsNullOrderByCreatedAtDesc(UUID quizId, Pageable pageable);
    long countByQuizIdAndDeletedAtIsNull(UUID quizId);

    @Query("select coalesce(sum(r.rating), 0) from Rating r where r.quizId = :quizId and r.deletedAt is null")
    Long sumActiveRatings(UUID quizId);
}
