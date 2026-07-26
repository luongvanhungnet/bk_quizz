package com.genquiz.bk.quiz;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
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
}
