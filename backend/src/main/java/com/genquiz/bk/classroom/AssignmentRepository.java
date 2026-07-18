package com.genquiz.bk.classroom;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface AssignmentRepository extends JpaRepository<Assignment, UUID> {
    Optional<Assignment> findByIdAndDeletedAtIsNull(UUID id);
    Page<Assignment> findByClassroomIdAndDeletedAtIsNull(UUID classroomId, Pageable pageable);
}
