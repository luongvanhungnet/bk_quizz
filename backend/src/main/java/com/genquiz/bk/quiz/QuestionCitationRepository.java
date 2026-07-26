package com.genquiz.bk.quiz;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface QuestionCitationRepository extends JpaRepository<QuestionCitation, UUID> {
    List<QuestionCitation> findByQuestionIdOrderByRoleAscPositionAsc(UUID questionId);
    List<QuestionCitation> findByQuestionIdInOrderByQuestionIdAscRoleAscPositionAsc(List<UUID> questionIds);
    void deleteByQuestionId(UUID questionId);
    void deleteByQuestionIdIn(List<UUID> questionIds);
}
