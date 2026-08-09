package com.genquiz.bk.source;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "source_documents")
public class SourceDocument {
    @Id
    private UUID id;

    @Column(name = "topic_id", nullable = false, updatable = false)
    private UUID topicId;

    @Column(name = "owner_id", nullable = false, updatable = false)
    private UUID ownerId;

    @Enumerated(EnumType.STRING)
    @Column(name = "source_type", nullable = false, length = 30)
    private SourceKind kind;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private SourceStatus status;

    @Column(name = "display_name", nullable = false, length = 255)
    private String name;

    @Column(name = "media_type", length = 150)
    private String contentType;

    @Column(name = "size_bytes")
    private Long sizeBytes;

    @Column(name = "storage_key", length = 600)
    private String objectKey;
    @Column(name="file_id") private UUID fileId;

    @Column(name = "extracted_text", columnDefinition = "text")
    private String extractedText;

    @Column(name = "error_code", length = 80)
    private String errorCode;

    @Column(name = "error_message", length = 1000)
    private String errorMessage;

    @Column(name = "rag_document_id") private UUID ragDocumentId;
    @Column(name = "rag_job_id") private UUID ragJobId;
    @Column(name = "indexing_progress", nullable = false) private int indexingProgress;
    @Column(name = "indexing_step", length = 64) private String indexingStep;
    @Column(name = "indexing_progress_at", nullable = false) private Instant indexingProgressAt;
    @Column(name = "page_count") private Integer pageCount;
    @Column(name = "chunk_count", nullable = false) private int chunkCount;
    @Column(name = "indexed_at") private Instant indexedAt;
    @Column(name = "math_extraction_status", nullable = false, length = 20) private String mathExtractionStatus = "NOT_DETECTED";
    @Column(name = "math_formula_count", nullable = false) private int mathFormulaCount;
    @Column(name = "math_warning_count", nullable = false) private int mathWarningCount;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected SourceDocument() {}

    public static SourceDocument pasted(UUID topicId, UUID ownerId, String name, String text) {
        SourceDocument source = base(topicId, ownerId, name, SourceKind.PASTE);
        source.status = SourceStatus.READY;
        source.contentType = "text/plain; charset=UTF-8";
        source.sizeBytes = (long) text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
        source.extractedText = text.trim();
        return source;
    }

    public static SourceDocument uploaded(UUID topicId, UUID ownerId, String name, String contentType,
                                          long sizeBytes, String objectKey) {
        SourceDocument source = base(topicId, ownerId, name, SourceKind.FILE);
        source.status = SourceStatus.UPLOADED;
        source.indexingProgress = 0;
        source.indexingStep = "QUEUED";
        source.contentType = contentType;
        source.sizeBytes = sizeBytes;
        source.objectKey = objectKey;
        return source;
    }

    private static SourceDocument base(UUID topicId, UUID ownerId, String name, SourceKind kind) {
        SourceDocument source = new SourceDocument();
        source.id = UUID.randomUUID();
        source.topicId = topicId;
        source.ownerId = ownerId;
        source.name = name.trim();
        source.kind = kind;
        source.status = SourceStatus.UPLOADED;
        source.createdAt = Instant.now();
        source.updatedAt = source.createdAt;
        source.indexingProgressAt = source.createdAt;
        return source;
    }

    public void completeExtraction(String text, Instant now) {
        if (text == null || text.trim().length() < 100) {
            throw new IllegalArgumentException("Tài liệu phải có ít nhất 100 ký tự hữu ích");
        }
        extractedText = text.trim();
        status = SourceStatus.READY;
        errorCode = null;
        errorMessage = null;
        updatedAt = now;
    }

    public void startRagIndex(UUID documentId, UUID jobId, Instant now) {
        ragDocumentId = documentId; ragJobId = jobId; status = SourceStatus.EMBEDDING;
        indexingProgress = 0; indexingStep = "PENDING"; indexingProgressAt = now; updatedAt = now;
    }

    public void beginRagUpload(Instant now) {
        status = SourceStatus.EXTRACTING;
        indexingProgress = Math.max(indexingProgress, 5);
        indexingStep = "UPLOADING_TO_RAG";
        indexingProgressAt = now;
        updatedAt = now;
    }

    public void beginRagSync(Instant now) {
        status = SourceStatus.EMBEDDING;
        indexingProgress = Math.max(indexingProgress, 95);
        indexingStep = "SYNCING";
        indexingProgressAt = now;
        updatedAt = now;
    }

    public void updateRagProgress(int progress, String step, Instant now) {
        int normalizedProgress = Math.max(0, Math.min(100, progress));
        boolean changed = status != SourceStatus.EMBEDDING
                || indexingProgress != normalizedProgress
                || !java.util.Objects.equals(indexingStep, step);
        if (!changed) return;
        status = SourceStatus.EMBEDDING;
        indexingProgress = normalizedProgress;
        indexingStep = step;
        indexingProgressAt = now;
        updatedAt = now;
    }

    public void completeRagIndex(int pages, int chunks, String indexedText, String mathStatus,
                                 int formulaCount, int warningCount, Instant now) {
        if (indexedText == null || indexedText.trim().length() < 100) {
            throw new IllegalArgumentException("Tài liệu phải có ít nhất 100 ký tự hữu ích");
        }
        extractedText = indexedText.trim();
        status = SourceStatus.READY; pageCount = pages > 0 ? pages : null; chunkCount = chunks;
        indexingProgress = 100; indexingStep = "SUCCEEDED"; indexedAt = now;
        indexingProgressAt = now;
        mathExtractionStatus = mathStatus == null ? "NOT_DETECTED" : mathStatus;
        mathFormulaCount = Math.max(0, formulaCount);
        mathWarningCount = Math.max(0, warningCount);
        errorCode = null; errorMessage = null; updatedAt = now;
    }

    public void queueReindex(Instant now) {
        ragDocumentId = null; ragJobId = null; status = SourceStatus.UPLOADED;
        indexingProgress = 0; indexingStep = "QUEUED"; indexingProgressAt = now;
        errorCode = null; errorMessage = null; updatedAt = now;
    }

    public void fail(String safeCode, String safeMessage, Instant now) {
        status = SourceStatus.FAILED;
        indexingStep = "FAILED";
        indexingProgressAt = now;
        errorCode = safeCode;
        errorMessage = safeMessage == null ? null : safeMessage.substring(0, Math.min(1000, safeMessage.length()));
        updatedAt = now;
    }

    public void softDelete() {
        status = SourceStatus.DELETED;
        deletedAt = Instant.now();
        updatedAt = deletedAt;
    }

    public boolean isOwnedBy(UUID actorId) { return ownerId.equals(actorId); }
    public UUID getId() { return id; }
    public UUID getTopicId() { return topicId; }
    public UUID getOwnerId() { return ownerId; }
    public SourceKind getKind() { return kind; }
    public SourceStatus getStatus() { return status; }
    public String getName() { return name; }
    public String getContentType() { return contentType; }
    public Long getSizeBytes() { return sizeBytes; }
    public String getObjectKey() { return objectKey; }
    public UUID getFileId(){return fileId;}
    public void attachFile(UUID id){this.fileId=id;}
    public String getExtractedText() { return extractedText; }
    public String getErrorCode() { return errorCode; }
    public String getErrorMessage() { return errorMessage; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
    public UUID getRagDocumentId() { return ragDocumentId; }
    public UUID getRagJobId() { return ragJobId; }
    public int getIndexingProgress() { return indexingProgress; }
    public String getIndexingStep() { return indexingStep; }
    public Instant getIndexingProgressAt() { return indexingProgressAt; }
    public Integer getPageCount() { return pageCount; }
    public int getChunkCount() { return chunkCount; }
    public Instant getIndexedAt() { return indexedAt; }
    public String getMathExtractionStatus() { return mathExtractionStatus; }
    public int getMathFormulaCount() { return mathFormulaCount; }
    public int getMathWarningCount() { return mathWarningCount; }
}
