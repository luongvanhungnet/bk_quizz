package com.genquiz.bk.source;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SourceDocumentStateTest {

    @Test
    void uploadedDocumentStartsQueuedInsteadOfExtracting() {
        SourceDocument source = SourceDocument.uploaded(
                UUID.randomUUID(),
                UUID.randomUUID(),
                "lesson.pdf",
                "application/pdf",
                1024,
                "source/lesson.pdf");

        assertEquals(SourceStatus.UPLOADED, source.getStatus());
        assertEquals("QUEUED", source.getIndexingStep());
        assertEquals(0, source.getIndexingProgress());
    }

    @Test
    void unchangedRemotePollDoesNotRefreshProgressTimestamp() {
        SourceDocument source = SourceDocument.uploaded(
                UUID.randomUUID(), UUID.randomUUID(), "lesson.pdf",
                "application/pdf", 1024, "source/lesson.pdf");
        Instant started = Instant.parse("2026-07-24T00:00:00Z");
        source.startRagIndex(UUID.randomUUID(), UUID.randomUUID(), started);

        source.updateRagProgress(0, "PENDING", started.plusSeconds(60));

        assertEquals(started, source.getIndexingProgressAt());
    }
}
