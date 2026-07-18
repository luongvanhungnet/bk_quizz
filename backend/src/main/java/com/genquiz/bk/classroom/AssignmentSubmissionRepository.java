package com.genquiz.bk.classroom;

import com.genquiz.bk.attempt.Attempt;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

import java.util.UUID;

public interface AssignmentSubmissionRepository extends Repository<Attempt, UUID> {
    Page<Attempt> findByAssignmentIdOrderByStartedAtDesc(UUID assignmentId, Pageable pageable);
}
