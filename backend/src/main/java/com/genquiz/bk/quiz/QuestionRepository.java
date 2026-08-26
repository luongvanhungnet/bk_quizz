package com.genquiz.bk.quiz;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
public interface QuestionRepository extends JpaRepository<Question, UUID> {
    interface QuizQuestionCount {
        UUID getQuizId();
        long getQuestionCount();
    }
    List<Question> findByQuizIdOrderByPosition(UUID quizId);
    Optional<Question> findByIdAndQuizId(UUID id, UUID quizId);
    long countByQuizId(UUID quizId);
    @Query("select q.quizId as quizId, count(q) as questionCount from Question q where q.quizId in :quizIds group by q.quizId")
    List<QuizQuestionCount> countByQuizIds(Collection<UUID> quizIds);
    void deleteByQuizId(UUID quizId);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update Question q set q.position = q.position + :offset "
            + "where q.quizId = :quizId and q.position > :deletedPosition")
    int movePositionsAfterToTemporaryRange(
            @Param("quizId") UUID quizId,
            @Param("deletedPosition") int deletedPosition,
            @Param("offset") int offset);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update Question q set q.position = q.position - :offset - 1 "
            + "where q.quizId = :quizId and q.position >= :offset")
    int restoreTemporaryPositionsAfterDelete(
            @Param("quizId") UUID quizId,
            @Param("offset") int offset);
}
