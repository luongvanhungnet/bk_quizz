package com.genquiz.bk.attempt;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface AttemptAnswerRepository extends JpaRepository<AttemptAnswer, UUID> {
    List<AttemptAnswer> findByAttemptId(UUID attemptId);
    Optional<AttemptAnswer> findByAttemptIdAndSnapshotId(UUID attemptId, UUID snapshotId);
}
