package com.genquiz.bk.job;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
public interface JobRepository extends JpaRepository<Job, UUID> {
    Optional<Job> findByIdAndSubjectUserId(UUID id, UUID subjectUserId);
    Optional<Job> findByIdempotencyKey(String idempotencyKey);

    @Query(value = """
            select * from jobs
             where status in ('QUEUED', 'RETRY') and available_at <= :now
             order by available_at, created_at
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
}
