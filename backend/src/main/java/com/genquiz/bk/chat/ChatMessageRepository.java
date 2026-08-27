package com.genquiz.bk.chat;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatMessageRepository extends JpaRepository<ChatMessage, UUID> {
    List<ChatMessage> findByThreadIdOrderByCreatedAt(UUID threadId);
    Optional<ChatMessage> findByIdAndThreadId(UUID id, UUID threadId);
    Optional<ChatMessage> findByThreadIdAndClientMessageId(UUID threadId, UUID clientMessageId);
    Optional<ChatMessage> findByThreadIdAndReplyToMessageId(UUID threadId, UUID replyToMessageId);
    boolean existsByThreadIdAndRoleAndStatusIn(UUID threadId, ChatRole role, List<ChatMessageStatus> statuses);
}
