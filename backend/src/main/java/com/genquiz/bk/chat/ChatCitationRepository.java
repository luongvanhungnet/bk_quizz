package com.genquiz.bk.chat;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatCitationRepository extends JpaRepository<ChatCitation, UUID> {
    List<ChatCitation> findByMessageIdInOrderByMessageIdAscCitationIndexAsc(Collection<UUID> messageIds);
    List<ChatCitation> findByMessageIdOrderByCitationIndex(UUID messageId);
    void deleteByMessageId(UUID messageId);
}
