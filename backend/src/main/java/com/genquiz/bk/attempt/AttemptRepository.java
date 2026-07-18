package com.genquiz.bk.attempt;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
public interface AttemptRepository extends JpaRepository<Attempt, UUID> {
    Optional<Attempt> findByIdAndUserId(UUID id, UUID userId);
    Page<Attempt> findByUserIdOrderByStartedAtDesc(UUID userId, Pageable pageable);
    boolean existsByAssignmentIdAndUserIdAndStatus(UUID assignmentId, UUID userId, AttemptStatus status);
    long countByAssignmentIdAndUserIdAndStatus(UUID assignmentId, UUID userId, AttemptStatus status);

    @Query("select coalesce(max(a.attemptNumber), 0) from Attempt a where a.quizId = :quizId " +
            "and a.userId = :userId and a.assignmentId is null")
    int maxPracticeAttemptNumber(@Param("quizId") UUID quizId, @Param("userId") UUID userId);

    @Query("select coalesce(max(a.attemptNumber), 0) from Attempt a where a.assignmentId = :assignmentId " +
            "and a.userId = :userId")
    int maxAssignmentAttemptNumber(@Param("assignmentId") UUID assignmentId, @Param("userId") UUID userId);

    long countByUserIdAndStatus(UUID userId, AttemptStatus status);
    Page<Attempt> findByQuizIdAndStatusOrderBySubmittedAtDesc(UUID quizId, AttemptStatus status, Pageable pageable);
    java.util.List<Attempt> findByQuizIdAndStatus(UUID quizId, AttemptStatus status);

    interface QuestionAccuracyRow {
        UUID getQuestionId();
        String getPrompt();
        long getAnswerCount();
        long getCorrectCount();
    }

    @Query(value = """
            select coalesce(s.source_question_id, s.id) as questionId,
                   min(s.prompt) as prompt,
                   count(ans.id) as answerCount,
                   count(ans.id) filter (where ans.is_correct = true) as correctCount
            from attempts a
            join attempt_question_snapshots s on s.attempt_id = a.id
            left join attempt_answers ans on ans.attempt_id = a.id and ans.question_snapshot_id = s.id
            where a.quiz_id = :quizId and a.status = 'SUBMITTED'
            group by coalesce(s.source_question_id, s.id)
            order by min(s.position), coalesce(s.source_question_id, s.id)
            """, nativeQuery = true)
    java.util.List<QuestionAccuracyRow> questionAccuracy(@Param("quizId") UUID quizId);

    @Query(value = """
            select cast(coalesce(round(avg(percentage), 2), 0) as numeric(5, 2))
            from attempts
            where user_id = :userId and status = 'SUBMITTED'
            """, nativeQuery = true)
    java.math.BigDecimal averagePercentage(@Param("userId") UUID userId);

    @Query("""
            select new com.genquiz.bk.attempt.DashboardActivityRow(
                a.id, a.quizId,
                case when q.title is null then 'Quiz đã xóa' else q.title end,
                a.status, a.percentage, coalesce(a.submittedAt, a.startedAt))
            from Attempt a
            left join Quiz q on q.id = a.quizId
            where a.userId = :userId
            order by coalesce(a.submittedAt, a.startedAt) desc
            """)
    java.util.List<DashboardActivityRow> findDashboardActivities(
            @Param("userId") UUID userId, Pageable pageable);

    @Query(value = "select count(distinct a.user_id) from attempts a join quizzes q on q.id = a.quiz_id " +
            "where q.topic_id = :topicId and a.status = 'SUBMITTED'", nativeQuery = true)
    long countDistinctLearnersByTopic(@Param("topicId") UUID topicId);
}
