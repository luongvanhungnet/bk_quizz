package com.genquiz.bk.community;

import com.genquiz.bk.attempt.Attempt;
import com.genquiz.bk.attempt.AttemptStatus;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;

import java.util.Optional;
import java.util.UUID;

public interface CommunityAttemptRepository extends Repository<Attempt, UUID> {
    Optional<Attempt> findByIdAndUserIdAndQuizIdAndStatus(UUID id, UUID userId, UUID quizId, AttemptStatus status);
    boolean existsByQuizIdAndUserIdAndStatus(UUID quizId, UUID userId, AttemptStatus status);
    long countByQuizIdAndStatus(UUID quizId, AttemptStatus status);

    @Query("select count(distinct a.userId) from Attempt a where a.quizId = :quizId " +
            "and a.status = com.genquiz.bk.attempt.AttemptStatus.SUBMITTED")
    long countDistinctLearners(UUID quizId);
}
