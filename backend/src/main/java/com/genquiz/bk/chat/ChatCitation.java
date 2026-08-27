package com.genquiz.bk.chat;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "chat_citations")
public class ChatCitation {
    @Id private UUID id;
    @Column(name = "message_id", nullable = false, updatable = false) private UUID messageId;
    @Column(name = "source_chunk_id", updatable = false) private UUID sourceChunkId;
    @Column(name = "citation_index", nullable = false) private int citationIndex;
    @Column(name = "quote_excerpt", columnDefinition = "text") private String quoteExcerpt;
    @Column(name = "relevance_score") private Float relevanceScore;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb") private String metadata = "{}";
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "citation_snapshot", nullable = false, columnDefinition = "jsonb")
    private String citationSnapshot = "{}";
    @Column(name = "created_at", nullable = false, updatable = false) private Instant createdAt;
    protected ChatCitation() {}
    public ChatCitation(UUID messageId, UUID sourceChunkId, int citationIndex, String excerpt,
                        Float relevanceScore, String citationSnapshot) {
        this.id = UUID.randomUUID(); this.messageId = messageId; this.sourceChunkId = sourceChunkId;
        this.citationIndex = citationIndex; this.quoteExcerpt = excerpt; this.relevanceScore = relevanceScore;
        this.citationSnapshot = citationSnapshot == null ? "{}" : citationSnapshot;
        this.createdAt = Instant.now();
    }
    public UUID getId() { return id; } public UUID getMessageId() { return messageId; }
    public UUID getSourceChunkId() { return sourceChunkId; } public int getCitationIndex() { return citationIndex; }
    public String getQuoteExcerpt() { return quoteExcerpt; } public Float getRelevanceScore() { return relevanceScore; }
    public String getCitationSnapshot() { return citationSnapshot; }
}
