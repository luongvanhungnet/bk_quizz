package com.genquiz.bk.source;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
public interface SourceChunkRepository extends JpaRepository<SourceChunk, UUID> {
    @Query("select c from SourceChunk c where c.sourceDocumentId = :sourceDocumentId and c.activeSnapshot = true order by c.chunkIndex")
    List<SourceChunk> findBySourceDocumentIdOrderByChunkIndex(UUID sourceDocumentId);
    @Modifying
    @Query("update SourceChunk c set c.activeSnapshot = false where c.sourceDocumentId = :sourceDocumentId and c.activeSnapshot = true")
    void deactivateBySourceDocumentId(UUID sourceDocumentId);
    @Modifying
    @Query("update SourceChunk c set c.activeSnapshot = false where c.sourceDocumentId = :sourceDocumentId and c.chunkIndex = :chunkIndex and c.activeSnapshot = true")
    void deactivateActiveAtIndex(UUID sourceDocumentId, int chunkIndex);
    void deleteBySourceDocumentId(UUID sourceDocumentId);
}
