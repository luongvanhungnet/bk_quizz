package com.genquiz.bk.rag;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.genquiz.bk.config.RagProperties;
import com.genquiz.bk.job.JobEventLevel;
import com.genquiz.bk.job.JobEventService;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
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
    void rejectsAnIncompatibleQuizGenerationContractBeforeGeneration() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/capabilities", exchange -> {
            byte[] body = """
                    {"quizGenerationContract":"legacy-v0","capabilities":{},
                     "buildRevision":"old-build"}
                    """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
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

        RagServiceException error = assertThrows(
                RagServiceException.class,
                client::requireQuizGenerationContract);

        assertEquals("RAG_CONTRACT_MISMATCH", error.code());
        assertTrue(error.retryable());
        assertEquals("old-build", error.details().path("actualBuildRevision").stringValue());
    }

    @Test
    void treatsAMissingCapabilitiesEndpointAsAContractMismatch() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/capabilities", exchange -> {
            byte[] body = """
                    {"status":"error","code":"HTTP_ERROR",
                     "message":"Không tìm thấy endpoint được yêu cầu."}
                    """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(404, body.length);
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

        RagServiceException error = assertThrows(
                RagServiceException.class,
                client::requireQuizGenerationContract);

        assertEquals("RAG_CONTRACT_MISMATCH", error.code());
        assertEquals("endpoint-missing", error.details().path("actualContract").stringValue());
    }

    @Test
    void preservesUtf8ErrorAndUpstreamRequestId() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/user-rag/generate-quiz", exchange -> {
            byte[] body = """
                    {"requestId":"rag-request-123","status":422,
                     "code":"RAG_DOCUMENT_TEXT_INSUFFICIENT",
                     "message":"Tài liệu có quá ít nội dung hữu ích để sinh quiz.",
                     "retryable":false,"retryAfterSeconds":null,
                     "details":[{"field":"acceptedQuestions","type":"list_type",
                     "message":"Input should be a valid list"}]}
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
        assertNotNull(error.details());
        assertEquals("acceptedQuestions", error.details().path(0).path("field").stringValue());
    }

    @Test
    void classifiesLegacyCognitiveValidationAsContractError() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/user-rag/generate-quiz", exchange -> {
            byte[] body = """
                    {"requestId":"job-contract-123","status":422,
                     "code":"VALIDATION_ERROR",
                     "message":"Dữ liệu gửi lên không hợp lệ.",
                     "retryable":false,"retryAfterSeconds":null,
                     "details":[{"field":"","message":"difficultyPlan chỉ nhận EASY, MEDIUM hoặc HARD.",
                     "type":"value_error"}]}
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
                "MIXED",
                new RagDtos.Counts(1, 0, 0));

        RagServiceException error = assertThrows(
                RagServiceException.class,
                () -> client.generate(UUID.randomUUID(), request));

        assertEquals("COGNITIVE_PLAN_INVALID", error.code());
        assertEquals("job-contract-123", error.upstreamRequestId());
        assertFalse(error.retryable());
    }

    @Test
    void readsFragmentedNdjsonAndPersistsProgressBeforeResult() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/user-rag/generate-quiz/stream", exchange -> {
            String heartbeat = "{\"type\":\"HEARTBEAT\",\"level\":\"INFO\"}\n";
            String event = "{\"type\":\"FALLBACK_STARTED\",\"level\":\"WARNING\","
                    + "\"message\":\"Đang chuyển sang Ollama Qwen.\",\"provider\":\"ollama\","
                    + "\"batchIndex\":0,\"requestId\":\"rag-stream-1\"}\n";
            String checkpoint = "{\"type\":\"STRUCTURED_OUTPUT_CHECKPOINT\","
                    + "\"acceptedQuestions\":[{\"planSlotId\":\"B1Q1\"}],"
                    + "\"model\":\"gemini-test\","
                    + "\"usage\":{\"inputTokens\":10,\"outputTokens\":20,\"totalTokens\":30}}\n";
            String result = "{\"type\":\"RESULT\",\"level\":\"SUCCESS\","
                    + "\"message\":\"Hoàn tất\",\"data\":{\"questions\":[],"
                    + "\"model\":\"qwen3:1.7b\",\"usage\":{\"totalTokens\":10}}}\n";
            byte[] first = (heartbeat + event.substring(0, event.length() / 2))
                    .getBytes(StandardCharsets.UTF_8);
            byte[] second = (event.substring(event.length() / 2) + checkpoint + result)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/x-ndjson; charset=utf-8");
            exchange.sendResponseHeaders(200, 0);
            exchange.getResponseBody().write(first);
            exchange.getResponseBody().flush();
            exchange.getResponseBody().write(second);
            exchange.close();
        });
        server.start();
        var properties = new RagProperties(
                true,
                "http://127.0.0.1:" + server.getAddress().getPort(),
                "internal-key",
                Duration.ofSeconds(2),
                Duration.ofSeconds(2));
        JobEventService events = mock(JobEventService.class);
        var client = new RagClient(properties, new ObjectMapper(), events);
        UUID jobId = UUID.randomUUID();
        var checkpoints = new ArrayList<tools.jackson.databind.JsonNode>();

        RagDtos.GeneratedQuiz result = client.generateStreaming(
                UUID.randomUUID(),
                jobId,
                new RagDtos.GenerateRequest(
                         List.of(UUID.randomUUID()), "Quiz", "EASY",
                        new RagDtos.Counts(1, 0, 0)),
                checkpoints::add);

        assertEquals("qwen3:1.7b", result.model());
        assertEquals("STRUCTURED_OUTPUT_CHECKPOINT",
                checkpoints.get(0).path("type").stringValue());
        assertEquals("B1Q1", checkpoints.get(0)
                .path("acceptedQuestions").get(0).path("planSlotId").stringValue());
        assertEquals(30, checkpoints.get(0).path("usage").path("totalTokens").asInt());
        verify(events).record(
                eq(jobId),
                eq(JobEventLevel.WARNING),
                eq("FALLBACK_STARTED"),
                eq("Đang chuyển sang Ollama Qwen."),
                eq(null),
                eq("ollama"),
                eq(0),
                eq(null),
                eq("rag-stream-1"),
                any());
        verify(events, never()).record(
                eq(jobId), any(), eq("HEARTBEAT"), any(), any(), any(),
                any(), any(), any(), any());
    }

    @Test
    void streamingFailurePreservesProviderErrorCodeAndRequestId() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/user-rag/generate-quiz/stream", exchange -> {
            String failed = "{\"type\":\"FAILED\",\"level\":\"ERROR\","
                    + "\"message\":\"Gemini không tương thích với request.\","
                    + "\"errorCode\":\"LLM_PROVIDER_REQUEST_INCOMPATIBLE\","
                    + "\"retryable\":false,\"requestId\":\"rag-provider-400\"}\n";
            byte[] bytes = failed.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/x-ndjson; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        var properties = new RagProperties(
                true,
                "http://127.0.0.1:" + server.getAddress().getPort(),
                "internal-key",
                Duration.ofSeconds(2),
                Duration.ofSeconds(2));
        JobEventService events = mock(JobEventService.class);
        var client = new RagClient(properties, new ObjectMapper(), events);
        UUID jobId = UUID.randomUUID();

        RagServiceException error = assertThrows(
                RagServiceException.class,
                () -> client.generateStreaming(
                        UUID.randomUUID(),
                        jobId,
                        new RagDtos.GenerateRequest(
                                List.of(UUID.randomUUID()), "Quiz", "EASY",
                                new RagDtos.Counts(1, 0, 0))));

        assertEquals("LLM_PROVIDER_REQUEST_INCOMPATIBLE", error.code());
        assertEquals("rag-provider-400", error.upstreamRequestId());
        assertFalse(error.retryable());
        verify(events).record(
                eq(jobId), eq(JobEventLevel.ERROR), eq("FAILED"),
                eq("Gemini không tương thích với request."), eq(null),
                eq(null), eq(null), eq(null), eq("rag-provider-400"), any());
    }

    @Test
    void streamingHttpValidationFailurePersistsSafeDetails() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/user-rag/generate-quiz/stream", exchange -> {
            byte[] body = """
                    {"requestId":"rag-validation-422","status":422,
                     "code":"VALIDATION_ERROR","message":"Dữ liệu gửi lên không hợp lệ.",
                     "retryable":false,"retryAfterSeconds":null,
                     "details":[{"field":"acceptedQuestions","type":"list_type",
                     "message":"Input should be a valid list"}]}
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
        JobEventService events = mock(JobEventService.class);
        var client = new RagClient(properties, new ObjectMapper(), events);
        UUID jobId = UUID.randomUUID();

        RagServiceException error = assertThrows(
                RagServiceException.class,
                () -> client.generateStreaming(
                        UUID.randomUUID(), jobId,
                        new RagDtos.GenerateRequest(
                                List.of(UUID.randomUUID()), "Quiz", "EASY",
                                new RagDtos.Counts(1, 0, 0))));

        assertEquals("VALIDATION_ERROR", error.code());
        assertEquals("acceptedQuestions", error.details().path(0).path("field").stringValue());
        verify(events).record(
                eq(jobId), eq(JobEventLevel.ERROR), eq("VALIDATION_ERROR"),
                eq("Dữ liệu gửi lên không hợp lệ."), eq(null), eq(null),
                eq(null), eq(null), eq("rag-validation-422"), any());
    }

    @Test
    void classifiesAStreamReadTimeoutSeparatelyFromAnInterruptedNdjsonStream()
            throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v2/user-rag/generate-quiz/stream", exchange -> {
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/x-ndjson; charset=utf-8");
            exchange.sendResponseHeaders(200, 0);
            try {
                Thread.sleep(300);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
            exchange.close();
        });
        server.start();
        var properties = new RagProperties(
                true,
                "http://127.0.0.1:" + server.getAddress().getPort(),
                "internal-key",
                Duration.ofSeconds(2),
                Duration.ofMillis(75));
        var client = new RagClient(
                properties, new ObjectMapper(), mock(JobEventService.class));

        RagServiceException error = assertThrows(
                RagServiceException.class,
                () -> client.generateStreaming(
                        UUID.randomUUID(), UUID.randomUUID(),
                        new RagDtos.GenerateRequest(
                                List.of(UUID.randomUUID()), "Quiz", "EASY",
                                new RagDtos.Counts(1, 0, 0))));

        assertEquals("RAG_STREAM_READ_TIMEOUT", error.code());
        assertTrue(error.retryable());
    }
}
