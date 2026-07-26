package com.genquiz.bk.source;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobService;
import com.genquiz.bk.job.JobType;
import com.genquiz.bk.topic.TopicService;
import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import com.genquiz.bk.storage.StoredFile;
import com.genquiz.bk.storage.StoredFileRepository;
import com.genquiz.bk.rag.RagDtos;

@Service
public class SourceService {
    public static final long MAX_UPLOAD_BYTES = 50L * 1024 * 1024;
    private static final Set<String> ALLOWED_TYPES = Set.of(
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "text/plain");

    private final SourceDocumentRepository sources;
    private final SourceChunkRepository chunks;
    private final TopicService topics;
    private final SourceObjectStorage storage;
    private final JobService jobs;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transactionTemplate;
    private final StoredFileRepository storedFiles;

    public SourceService(SourceDocumentRepository sources, SourceChunkRepository chunks, TopicService topics,
                         ObjectProvider<SourceObjectStorage> storage, JobService jobs, ObjectMapper objectMapper,
                         PlatformTransactionManager transactionManager, StoredFileRepository storedFiles) {
        this.sources = sources;
        this.chunks = chunks;
        this.topics = topics;
        this.storage = storage.getIfAvailable();
        this.jobs = jobs;
        this.objectMapper = objectMapper;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.storedFiles=storedFiles;
    }

    @Transactional
    public SourceDocument paste(UUID actorId, UUID topicId, SourceDtos.PasteRequest request) {
        topics.getOwned(actorId, topicId);
        SourceDocument source = sources.save(SourceDocument.pasted(topicId, actorId, request.name(), request.text()));
        source.queueReindex(Instant.now());
        jobs.enqueue(JobType.SOURCE_INGESTION, actorId, source.getId(), jsonPayload(source),
                "source-ingestion:" + source.getId(), 3);
        return source;
    }

    public UploadResult upload(UUID actorId, UUID topicId, MultipartFile file, String idempotencyKey) {
        topics.getOwned(actorId, topicId);
        validateUpload(file);
        if (storage == null) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Dịch vụ lưu trữ tài liệu chưa được cấu hình");
        }
        SourceObjectStorage.StoredObject stored;
        try {
            stored = storage.scanAndStore(file.getOriginalFilename(), file.getContentType(), file.getSize(),
                    file.getInputStream());
        } catch (IOException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Không thể lưu tài liệu", exception);
        }
        try {
            UploadResult result = transactionTemplate.execute(status ->
                    persistUploaded(actorId, topicId, file, stored, idempotencyKey));
            if (result == null) throw new IllegalStateException("Không thể ghi nhận tài liệu");
            return result;
        } catch (RuntimeException exception) {
            storage.delete(stored.objectKey());
            throw exception;
        }
    }

    private UploadResult persistUploaded(UUID actorId, UUID topicId, MultipartFile file,
                                         SourceObjectStorage.StoredObject stored, String idempotencyKey) {
        SourceDocument source = sources.save(SourceDocument.uploaded(topicId, actorId,
                safeName(file.getOriginalFilename()), stored.detectedContentType(), file.getSize(), stored.objectKey()));
        StoredFile record=storedFiles.save(new StoredFile(actorId,StoredFile.Purpose.SOURCE,
                StoredFile.Provider.valueOf(stored.provider()),stored.objectKey(),safeName(file.getOriginalFilename()),
                file.getContentType(),stored.detectedContentType(),file.getSize(),stored.sha256(),false));
        source.attachFile(record.getId());
        Job job = jobs.enqueue(JobType.SOURCE_INGESTION, actorId, source.getId(),
                jsonPayload(source), idempotencyKey, 3);
        return new UploadResult(source, job);
    }

    @Transactional(readOnly = true)
    public List<SourceDocument> list(UUID actorId, UUID topicId) {
        topics.getOwned(actorId, topicId);
        return sources.findByTopicIdAndDeletedAtIsNullOrderByCreatedAtDesc(topicId);
    }

    @Transactional(readOnly = true)
    public SourceDocument getOwned(UUID actorId, UUID sourceId) {
        SourceDocument source = sources.findByIdAndDeletedAtIsNull(sourceId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy tài liệu"));
        if (!source.isOwnedBy(actorId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Bạn không có quyền xem tài liệu này");
        }
        return source;
    }

    @Transactional
    public void completeExtraction(UUID sourceId, String extractedText) {
        SourceDocument source = require(sourceId);
        source.completeExtraction(extractedText, Instant.now());
        chunks.deleteBySourceDocumentId(sourceId);
        chunks.saveAll(chunk(sourceId, source.getTopicId(), extractedText));
    }

    @Transactional(readOnly = true)
    public SourceDocument getForWorker(UUID sourceId) { return require(sourceId); }

    @Transactional
    public void beginRagUpload(UUID sourceId) {
        require(sourceId).beginRagUpload(Instant.now());
    }

    @Transactional
    public Job startRagIndex(UUID sourceId, RagDtos.Upload upload) {
        SourceDocument source = require(sourceId);
        source.startRagIndex(upload.documentId(), upload.jobId(), Instant.now());
        String payload = "{\"sourceDocumentId\":\"" + sourceId + "\"}";
        return jobs.enqueue(JobType.RAG_INDEX_POLL, source.getOwnerId(), sourceId, payload,
                "rag-index-poll:" + sourceId + ":" + upload.jobId(), 120);
    }

    @Transactional
    public void updateRagProgress(UUID sourceId, int progress, String step) {
        require(sourceId).updateRagProgress(progress, step, Instant.now());
    }

    @Transactional
    public void beginRagSync(UUID sourceId) {
        require(sourceId).beginRagSync(Instant.now());
    }

    @Transactional
    public void completeRagIndex(UUID sourceId, RagDtos.Document document, List<RagDtos.Chunk> ragChunks) {
        SourceDocument source = require(sourceId);
        String indexedText = ragChunks.stream()
                .map(RagDtos.Chunk::text)
                .collect(java.util.stream.Collectors.joining("\n\n"));
        chunks.deleteBySourceDocumentId(sourceId);
        chunks.saveAll(ragChunks.stream().map(chunk -> new SourceChunk(chunk.chunkId(), sourceId,
                source.getTopicId(), chunk.chunkIndex(), chunk.text(), Math.max(1, chunk.text().split("\\s+").length),
                chunk.pageNumber(), chunk.slideNumber(), chunk.heading())).toList());
        source.completeRagIndex(document.pageCount() == null ? 0 : document.pageCount(), ragChunks.size(),
                indexedText, Instant.now());
    }

    @Transactional
    public Job reindex(UUID actorId, UUID sourceId) {
        SourceDocument source = getOwned(actorId, sourceId);
        source.queueReindex(Instant.now());
        return jobs.enqueue(JobType.SOURCE_INGESTION, actorId, sourceId, jsonPayload(source),
                "source-reindex:" + sourceId + ":" + source.getVersion(), 3);
    }

    @Transactional
    public void markFailed(UUID sourceId, String code, String message) {
        require(sourceId).fail(code, message, Instant.now());
    }

    @Transactional
    public void delete(UUID actorId, UUID sourceId) {
        getOwned(actorId, sourceId).softDelete();
    }

    private SourceDocument require(UUID sourceId) {
        return sources.findByIdAndDeletedAtIsNull(sourceId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy tài liệu"));
    }

    private static void validateUpload(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Vui lòng chọn tài liệu");
        }
        if (file.getSize() > MAX_UPLOAD_BYTES) {
            throw new ResponseStatusException(HttpStatus.CONTENT_TOO_LARGE, "Tài liệu vượt quá giới hạn 50 MB");
        }
        if (file.getContentType() == null || !ALLOWED_TYPES.contains(file.getContentType())) {
            throw new ResponseStatusException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "Định dạng tài liệu không được hỗ trợ");
        }
    }

    private static String safeName(String name) {
        if (name == null || name.isBlank()) return "tai-lieu";
        String base = name.replace('\\', '/');
        base = base.substring(base.lastIndexOf('/') + 1).trim();
        return base.substring(0, Math.min(255, base.length()));
    }

    private String jsonPayload(SourceDocument source) {
        try {
            return objectMapper.writeValueAsString(java.util.Map.of(
                    "sourceDocumentId", source.getId()));
        } catch (JacksonException exception) {
            throw new IllegalStateException("Không thể tạo payload xử lý tài liệu", exception);
        }
    }

    static List<SourceChunk> chunk(UUID sourceId, UUID topicId, String text) {
        String[] words = text.trim().split("\\s+");
        int size = 800;
        int overlap = 100;
        List<SourceChunk> result = new ArrayList<>();
        for (int start = 0, index = 0; start < words.length; start += size - overlap, index++) {
            int end = Math.min(words.length, start + size);
            String content = String.join(" ", java.util.Arrays.copyOfRange(words, start, end));
            result.add(new SourceChunk(sourceId, topicId, index, content, end - start));
            if (end == words.length) break;
        }
        return result;
    }

    public record UploadResult(SourceDocument source, Job job) {}
}
