package com.genquiz.bk.source;

import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobHandler;
import com.genquiz.bk.job.JobType;
import com.genquiz.bk.rag.RagClient;
import com.genquiz.bk.rag.RagServiceException;
import org.springframework.stereotype.Component;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

@Component
public class SourceIngestionHandler implements JobHandler {
    private final SourceObjectStorage storage;
    private final SourceService sources;
    private final RagClient rag;
    public SourceIngestionHandler(SourceObjectStorage storage, SourceService sources, RagClient rag) {
        this.storage = storage; this.sources = sources; this.rag = rag;
    }
    @Override public JobType type() { return JobType.SOURCE_INGESTION; }
    @Override public String handle(Job job) throws Exception {
        SourceDocument source = sources.getForWorker(job.getResourceId());
        var submitted = submit(source);
        var poll = sources.startRagIndex(source.getId(), submitted);
        return "{\"ragDocumentId\":\"" + submitted.documentId()
                + "\",\"pollJobId\":\"" + poll.getId() + "\"}";
    }

    private com.genquiz.bk.rag.RagDtos.Upload submit(SourceDocument source) throws Exception {
        if (source.getRagDocumentId() != null) {
            return rag.reindex(source.getOwnerId(), source.getRagDocumentId());
        }
        if (source.getIndexedAt() != null) {
            String hash = sources.storedFileHash(source.getId());
            if (hash != null) {
                try {
                    var resolved = rag.resolveDocument(source.getOwnerId(), hash);
                    sources.adoptRagDocument(source.getId(), resolved.id());
                    return rag.reindex(source.getOwnerId(), resolved.id());
                } catch (RagServiceException error) {
                    if (!"DOCUMENT_NOT_FOUND".equals(error.code())) throw error;
                }
            }
        }
        sources.beginRagUpload(source.getId());
        InputStream stream = source.getKind() == SourceKind.PASTE
                ? new ByteArrayInputStream(source.getExtractedText().getBytes(StandardCharsets.UTF_8))
                : storage.read(source.getObjectKey());
        try (InputStream input = stream) {
            return rag.upload(source.getOwnerId(), source.getName(), source.getContentType(), input,
                    "bkquiz-source-" + source.getId() + "-v" + source.getVersion());
        }
    }
}
