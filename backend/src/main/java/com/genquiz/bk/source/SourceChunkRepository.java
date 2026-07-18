package com.genquiz.bk.source;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface SourceChunkRepository extends JpaRepository<SourceChunk, UUID> {
    List<SourceChunk> findBySourceDocumentIdOrderByChunkIndex(UUID sourceDocumentId);
    void deleteBySourceDocumentId(UUID sourceDocumentId);
}
