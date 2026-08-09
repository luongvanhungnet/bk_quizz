package com.genquiz.bk.job;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.Set;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.domain.Pageable;
public interface JobRepository extends JpaRepository<Job, UUID> {
    Optional<Job> findByIdAndSubjectUserId(UUID id, UUID subjectUserId);
    Optional<Job> findByIdempotencyKey(String idempotencyKey);
    Optional<Job> findFirstByResourceIdAndSubjectUserIdAndTypeOrderByCreatedAtDesc(
            UUID resourceId, UUID subjectUserId, JobType type);
    List<Job> findByResourceIdAndSubjectUserIdAndTypeOrderByCreatedAtDesc(
            UUID resourceId, UUID subjectUserId, JobType type, Pageable pageable);
    boolean existsByResourceIdAndTypeAndStatusIn(
            UUID resourceId, JobType type, Set<JobStatus> statuses);

    @Query(value = """
            select * from jobs
             where status in ('QUEUED', 'RETRY') and available_at <= :now
             order by priority, available_at, created_at
             for update skip locked
             limit 1
            """, nativeQuery = true)
    Optional<Job> lockNextAvailable(@Param("now") Instant now);

    @Query("select j from Job j where j.status = com.genquiz.bk.job.JobStatus.RUNNING " +
            "and j.heartbeatAt < :staleBefore")
    List<Job> findStaleRunning(@Param("staleBefore") Instant staleBefore);

    @Modifying
    @Query("delete from Job j where j.completedAt < :before and j.status in " +
            "(com.genquiz.bk.job.JobStatus.SUCCEEDED, com.genquiz.bk.job.JobStatus.FAILED)")
    int deleteCompletedBefore(@Param("before") Instant before);

    @Query("select count(j) from Job j where j.type in :types and j.status in :statuses")
    long countByTypesAndStatuses(@Param("types") Set<JobType> types,
                                 @Param("statuses") Set<JobStatus> statuses);

    @Query("select min(j.createdAt) from Job j where j.type in :types and j.status in :statuses")
    Instant findOldestCreatedAt(@Param("types") Set<JobType> types,
                                @Param("statuses") Set<JobStatus> statuses);
}
