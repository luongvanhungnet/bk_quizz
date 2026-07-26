package com.genquiz.bk.source;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "source_chunks")
public class SourceChunk {
    @Id
    private UUID id;

    @Column(name = "document_id", nullable = false, updatable = false)
    private UUID sourceDocumentId;

    @Column(name = "topic_id", nullable = false, updatable = false)
    private UUID topicId;

    @Column(name = "chunk_index", nullable = false)
    private int chunkIndex;

    @Column(nullable = false, columnDefinition = "text")
    private String content;

    @Column(name = "token_count", nullable = false)
    private int tokenCount;
    @Column(name = "page_number") private Integer pageNumber;
    @Column(name = "slide_number") private Integer slideNumber;
    @Column(length = 1000) private String heading;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected SourceChunk() {}

    public SourceChunk(UUID sourceDocumentId, UUID topicId, int chunkIndex, String content, int tokenCount) {
        this.id = UUID.randomUUID();
        this.sourceDocumentId = sourceDocumentId;
        this.topicId = topicId;
        this.chunkIndex = chunkIndex;
        this.content = content;
        this.tokenCount = tokenCount;
        this.createdAt = Instant.now();
    }

    public SourceChunk(UUID id, UUID sourceDocumentId, UUID topicId, int chunkIndex, String content,
                       int tokenCount, Integer pageNumber, Integer slideNumber, String heading) {
        this(sourceDocumentId, topicId, chunkIndex, content, tokenCount);
        this.id = id; this.pageNumber = pageNumber; this.slideNumber = slideNumber; this.heading = heading;
    }

    public UUID getId() { return id; }
    public UUID getSourceDocumentId() { return sourceDocumentId; }
    public UUID getTopicId() { return topicId; }
    public int getChunkIndex() { return chunkIndex; }
    public String getContent() { return content; }
    public int getTokenCount() { return tokenCount; }
    public Integer getPageNumber() { return pageNumber; }
    public Integer getSlideNumber() { return slideNumber; }
    public String getHeading() { return heading; }
}
