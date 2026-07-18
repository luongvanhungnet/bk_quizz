package com.genquiz.bk.classroom;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ClassroomMemberRepository extends JpaRepository<ClassroomMember, UUID> {
    Optional<ClassroomMember> findByClassroomIdAndUserId(UUID classroomId, UUID userId);
    boolean existsByClassroomIdAndUserIdAndStatus(UUID classroomId, UUID userId, ClassroomMemberStatus status);
    List<ClassroomMember> findByClassroomIdAndStatusOrderByJoinedAtAsc(UUID classroomId, ClassroomMemberStatus status);
    long countByClassroomIdAndStatus(UUID classroomId, ClassroomMemberStatus status);
    List<ClassroomMember> findByUserIdAndStatus(UUID userId, ClassroomMemberStatus status);
}
