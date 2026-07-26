package com.genquiz.bk.rag;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.genquiz.bk.config.RagProperties;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class RagClientTest {
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) server.stop(0);
    }

    @Test
    void preservesUtf8ErrorAndUpstreamRequestId() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/user-rag/generate-quiz", exchange -> {
            byte[] body = """
                    {"requestId":"rag-request-123","status":422,
                     "code":"RAG_DOCUMENT_TEXT_INSUFFICIENT",
                     "message":"Tài liệu có quá ít nội dung hữu ích để sinh quiz.",
                     "retryable":false,"retryAfterSeconds":null,"details":[]}
                    """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(422, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        var properties = new RagProperties(
                true,
                "http://127.0.0.1:" + server.getAddress().getPort(),
                "internal-key",
                Duration.ofSeconds(2),
                Duration.ofSeconds(2));
        var client = new RagClient(properties, new ObjectMapper());
        var request = new RagDtos.GenerateRequest(
                List.of(UUID.randomUUID()),
                "Quiz",
                "EASY",
                new RagDtos.Counts(1, 0, 0));

        RagServiceException error = assertThrows(
                RagServiceException.class,
                () -> client.generate(UUID.randomUUID(), request));

        assertEquals("RAG_DOCUMENT_TEXT_INSUFFICIENT", error.code());
        assertEquals(
                "Tài liệu có quá ít nội dung hữu ích để sinh quiz.",
                error.getMessage());
        assertEquals("rag-request-123", error.upstreamRequestId());
        assertFalse(error.retryable());
    }
}
