package com.genquiz.bk.quiz;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface AcceptedAnswerRepository extends JpaRepository<AcceptedAnswer, UUID> {
    List<AcceptedAnswer> findByQuestionIdOrderByPosition(UUID questionId);
    List<AcceptedAnswer> findByQuestionIdInOrderByQuestionIdAscPositionAsc(Collection<UUID> questionIds);
    void deleteByQuestionId(UUID questionId);
    void deleteByQuestionIdIn(Collection<UUID> questionIds);
}
