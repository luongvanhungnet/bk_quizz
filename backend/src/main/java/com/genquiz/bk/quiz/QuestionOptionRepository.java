package com.genquiz.bk.quiz;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface QuestionOptionRepository extends JpaRepository<QuestionOption, UUID> {
    List<QuestionOption> findByQuestionIdOrderByPosition(UUID questionId);
    List<QuestionOption> findByQuestionIdInOrderByQuestionIdAscPositionAsc(Collection<UUID> questionIds);
    void deleteByQuestionId(UUID questionId);
    void deleteByQuestionIdIn(Collection<UUID> questionIds);
}
