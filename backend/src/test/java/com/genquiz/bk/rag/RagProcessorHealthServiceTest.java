package com.genquiz.bk.rag;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.genquiz.bk.config.RagProperties;
import java.time.Duration;
import java.util.Map;
import org.junit.jupiter.api.Test;

class RagProcessorHealthServiceTest {
    @Test
    void reportsTheQuizGenerationContractSeparatelyFromWorkerHealth() {
        RagClient client = mock(RagClient.class);
        when(client.health()).thenReturn(new RagDtos.Health(
                "ok", Map.of("celeryWorker", "UP"), 0, 0, 0, 0));
        when(client.capabilities()).thenReturn(new RagDtos.Capabilities(
                "legacy-v0", Map.of(), "old-build"));
        var properties = new RagProperties(
                true, "http://127.0.0.1:8090", "internal-key",
                Duration.ofSeconds(2), Duration.ofSeconds(2));
        var service = new RagProcessorHealthService(client, properties);

        service.refresh();

        assertTrue(service.snapshot().apiAvailable());
        assertTrue(service.snapshot().workerAvailable());
        assertFalse(service.snapshot().quizGenerationContractCompatible());
    }
}
