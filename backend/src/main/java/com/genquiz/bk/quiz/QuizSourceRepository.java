package com.genquiz.bk.quiz;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface QuizSourceRepository extends JpaRepository<QuizSource, UUID> {
    List<QuizSource> findByQuizId(UUID quizId);
    void deleteByQuizId(UUID quizId);
}
