package com.genquiz.bk.attempt;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface AttemptQuestionSnapshotRepository extends JpaRepository<AttemptQuestionSnapshot, UUID> {
    List<AttemptQuestionSnapshot> findByAttemptIdOrderByPosition(UUID attemptId);
    Optional<AttemptQuestionSnapshot> findByIdAndAttemptId(UUID id, UUID attemptId);
}
