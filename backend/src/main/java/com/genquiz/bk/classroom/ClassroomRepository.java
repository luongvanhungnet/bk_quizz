package com.genquiz.bk.classroom;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;
import java.util.UUID;

public interface ClassroomRepository extends JpaRepository<Classroom, UUID> {
    Optional<Classroom> findByIdAndDeletedAtIsNull(UUID id);
    Optional<Classroom> findByJoinCodeIgnoreCaseAndDeletedAtIsNull(String joinCode);
    boolean existsByJoinCodeIgnoreCaseAndDeletedAtIsNull(String joinCode);
    boolean existsByOwnerIdAndStatusAndDeletedAtIsNull(UUID ownerId, ClassroomStatus status);

    @Query("select c from Classroom c where c.deletedAt is null and exists " +
            "(select m.id from ClassroomMember m where m.classroomId = c.id " +
            "and m.userId = :userId and m.status = com.genquiz.bk.classroom.ClassroomMemberStatus.ACTIVE)")
    Page<Classroom> findActiveForMember(UUID userId, Pageable pageable);
}
