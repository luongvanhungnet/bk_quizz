package com.genquiz.bk.source;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface SourceDocumentRepository extends JpaRepository<SourceDocument, UUID> {
    List<SourceDocument> findByTopicIdAndDeletedAtIsNullOrderByCreatedAtDesc(UUID topicId);
    Optional<SourceDocument> findByIdAndDeletedAtIsNull(UUID id);
    Optional<SourceDocument> findByRagDocumentIdAndDeletedAtIsNull(UUID ragDocumentId);
    List<SourceDocument> findAllByIdInAndOwnerIdAndStatusAndDeletedAtIsNull(
            Collection<UUID> ids, UUID ownerId, SourceStatus status);
}
