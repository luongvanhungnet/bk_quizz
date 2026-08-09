package com.genquiz.bk.job;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JobEventRepository extends JpaRepository<JobEvent, Long> {
    List<JobEvent> findByJobIdAndIdGreaterThanOrderByIdAsc(
            UUID jobId, long afterId, Pageable pageable);

    Optional<JobEvent> findFirstByJobIdOrderByIdDesc(UUID jobId);
}
