package com.genquiz.bk.source;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.genquiz.bk.job.Job;
import com.genquiz.bk.rag.RagClient;
import com.genquiz.bk.rag.RagDtos;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SourceIngestionHandlerTest {
    @Test
    void reindexUsesExistingRagDocumentInsteadOfUploadingDuplicateFile() throws Exception {
        SourceObjectStorage storage = mock(SourceObjectStorage.class);
        SourceService sources = mock(SourceService.class);
        RagClient rag = mock(RagClient.class);
        Job sourceJob = mock(Job.class);
        Job pollJob = mock(Job.class);
        UUID ragDocumentId = UUID.randomUUID();
        UUID ragJobId = UUID.randomUUID();
        UUID ownerId = UUID.randomUUID();
        SourceDocument source = SourceDocument.uploaded(
                UUID.randomUUID(), ownerId, "lesson.pdf", "application/pdf",
                1024, "source/lesson.pdf");
        UUID sourceId = source.getId();
        source.startRagIndex(ragDocumentId, UUID.randomUUID(), Instant.now());
        source.completeRagIndex(
                1, 1,
                "Nội dung tài liệu đã lập chỉ mục đủ dài để kiểm tra rằng luồng reindex không tải file trùng lên RAG service.",
                "NOT_DETECTED", 0, 0, Instant.now());
        source.queueReindex(Instant.now());
        var response = new RagDtos.Upload(ragDocumentId, ragJobId, "READY", "PENDING");

        when(sourceJob.getResourceId()).thenReturn(sourceId);
        when(sources.getForWorker(sourceId)).thenReturn(source);
        when(rag.reindex(ownerId, ragDocumentId)).thenReturn(response);
        when(sources.startRagIndex(sourceId, response)).thenReturn(pollJob);
        when(pollJob.getId()).thenReturn(UUID.randomUUID());

        String result = new SourceIngestionHandler(storage, sources, rag).handle(sourceJob);

        verify(rag).reindex(ownerId, ragDocumentId);
        verify(rag, never()).upload(any(), any(), any(), any(), any());
        assertTrue(result.contains(ragDocumentId.toString()));
    }
}
