package com.genquiz.bk.quiz;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface QuestionRepository extends JpaRepository<Question, UUID> {
    List<Question> findByQuizIdOrderByPosition(UUID quizId);
    Optional<Question> findByIdAndQuizId(UUID id, UUID quizId);
    long countByQuizId(UUID quizId);
    void deleteByQuizId(UUID quizId);
}
