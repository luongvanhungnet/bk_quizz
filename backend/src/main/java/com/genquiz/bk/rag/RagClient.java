package com.genquiz.bk.rag;

import com.genquiz.bk.config.RagProperties;
import com.genquiz.bk.job.JobEventLevel;
import com.genquiz.bk.job.JobEventService;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URLEncoder;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.UUID;
import java.util.function.Consumer;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
public class RagClient {
    private final RagProperties properties;
    private final RestClient client;
    private final ObjectMapper mapper;
    private final JobEventService events;

    public RagClient(RagProperties properties, ObjectMapper mapper) {
        this(properties, mapper, null);
    }

    @Autowired
    public RagClient(
            RagProperties properties,
            ObjectMapper mapper,
            JobEventService events) {
        this.properties = properties;
        this.mapper = mapper;
        this.events = events;
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(properties.connectTimeout());
        factory.setReadTimeout(properties.readTimeout());
        this.client = RestClient.builder().baseUrl(properties.baseUrl().replaceAll("/$", "") + "/api/v2")
                .requestFactory(factory).build();
    }

    public boolean enabled() { return properties.enabled(); }

    public RagDtos.Upload upload(UUID userId, String filename, String contentType, InputStream input,
                                 String idempotencyKey) {
        requireEnabled();
        byte[] content;
        try {
            content = input.readAllBytes();
        } catch (java.io.IOException exception) {
            throw new RagServiceException("SOURCE_READ_FAILED", "Không thể đọc tệp đã lưu.", false,
                    null, null, exception);
        }
        MultipartBody body = multipart(filename, contentType, content);
        return call(() -> client.post().uri("/user-documents").headers(headers -> {
                    internal(headers, userId); headers.set("Idempotency-Key", idempotencyKey);
                }).contentType(MediaType.parseMediaType(body.contentType())).body(body.content())
                .retrieve().body(RagDtos.Upload.class));
    }

    public RagDtos.Health health() {
        requireEnabled();
        return client.get()
                .uri(properties.baseUrl().replaceAll("/$", "") + "/health/ready")
                .exchange((request, response) -> mapper.readValue(response.getBody(), RagDtos.Health.class));
    }

    public RagDtos.Capabilities capabilities() {
        requireEnabled();
        try {
            return call(() -> client.get()
                    .uri("/capabilities")
                    .headers(headers -> internalService(headers))
                    .retrieve()
                    .body(RagDtos.Capabilities.class));
        } catch (RagServiceException exception) {
            if ("RAG_ENDPOINT_NOT_FOUND".equals(exception.code())) {
                throw contractMismatch("endpoint-missing", "unknown", exception);
            }
            throw exception;
        }
    }

    public void requireQuizGenerationContract() {
        RagDtos.Capabilities current = capabilities();
        if (RagDtos.QUIZ_GENERATION_CONTRACT.equals(
                current.quizGenerationContract())
                && requiredQuizCapabilitiesAvailable(current.capabilities())) {
            return;
        }
        throw contractMismatch(
                current.quizGenerationContract(), current.buildRevision(), null);
    }

    private static boolean requiredQuizCapabilitiesAvailable(
            java.util.Map<String, Boolean> capabilities) {
        return capabilities != null && java.util.List.of(
                        "questionPlan", "acceptedQuestions", "streaming",
                        "partialCognitiveRepair", "structuredOutputCheckpoint")
                .stream()
                .allMatch(name -> Boolean.TRUE.equals(capabilities.get(name)));
    }

    private RagServiceException contractMismatch(
            String actualContract, String buildRevision, Throwable cause) {
        var details = mapper.createObjectNode();
        details.put("expectedContract", RagDtos.QUIZ_GENERATION_CONTRACT);
        details.put("actualContract", actualContract);
        details.put("actualBuildRevision", buildRevision);
        return new RagServiceException(
                "RAG_CONTRACT_MISMATCH",
                "Backend và dịch vụ RAG chưa dùng cùng contract sinh quiz.",
                true,
                Duration.ofMinutes(5),
                null,
                details,
                cause);
    }

    public RagDtos.IndexJob job(UUID userId, UUID jobId) {
        return call(() -> client.get().uri("/indexing-jobs/{id}", jobId)
                .headers(headers -> internal(headers, userId)).retrieve().body(RagDtos.IndexJob.class));
    }

    public RagDtos.Document document(UUID userId, UUID documentId) {
        return call(() -> client.get().uri("/user-documents/{id}", documentId)
                .headers(headers -> internal(headers, userId)).retrieve().body(RagDtos.Document.class));
    }

    public RagDtos.Chunks chunks(UUID userId, UUID documentId, int page) {
        return call(() -> client.get().uri(uri -> uri.path("/user-documents/{id}/chunks")
                        .queryParam("page", page).queryParam("size", 500).build(documentId))
                .headers(headers -> internal(headers, userId)).retrieve().body(RagDtos.Chunks.class));
    }

    public RagDtos.GeneratedQuiz generate(UUID userId, RagDtos.GenerateRequest request) {
        return call(() -> client.post().uri("/user-rag/generate-quiz")
                .headers(headers -> internal(headers, userId)).contentType(MediaType.APPLICATION_JSON)
                .body(request).retrieve().body(RagDtos.GeneratedQuiz.class));
    }

    public RagDtos.GeneratedQuiz generateStreaming(
            UUID userId,
            UUID jobId,
            RagDtos.GenerateRequest request) {
        return generateStreaming(userId, jobId, request, ignored -> {});
    }

    public RagDtos.GeneratedQuiz generateStreaming(
            UUID userId,
            UUID jobId,
            RagDtos.GenerateRequest request,
            Consumer<JsonNode> generationCheckpoint) {
        requireEnabled();
        try {
            return client.post()
                    .uri("/user-rag/generate-quiz/stream")
                    .headers(headers -> internal(headers, userId))
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.parseMediaType("application/x-ndjson"))
                    .body(request)
                    .exchange((httpRequest, response) -> {
                        if (response.getStatusCode().isError()) {
                            byte[] body = response.getBody().readAllBytes();
                            RagServiceException failure = decodeStreamingError(
                                    response.getStatusCode().value(), body, null);
                            persistHttpFailure(jobId, failure);
                            throw failure;
                        }
                        RagDtos.GeneratedQuiz generated = null;
                        boolean terminal = false;
                        try (var reader = new BufferedReader(new InputStreamReader(
                                response.getBody(), StandardCharsets.UTF_8))) {
                            String line;
                            while ((line = reader.readLine()) != null) {
                                if (line.isBlank()) continue;
                                JsonNode event = mapper.readTree(line);
                                String type = event.path("type").stringValue("");
                                if ("HEARTBEAT".equals(type)) {
                                    continue;
                                }
                                if ("COGNITIVE_CHECKPOINT".equals(type)
                                        || "CITATION_CHECKPOINT".equals(type)
                                        || "STRUCTURED_OUTPUT_CHECKPOINT".equals(type)) {
                                    JsonNode accepted = event.path("acceptedQuestions");
                                    if (accepted.isArray()) {
                                        generationCheckpoint.accept(
                                                "STRUCTURED_OUTPUT_CHECKPOINT".equals(type)
                                                        ? event.deepCopy()
                                                        : accepted.deepCopy());
                                    }
                                    continue;
                                }
                                if ("RESULT".equals(type)) {
                                    generated = mapper.treeToValue(
                                            event.path("data"), RagDtos.GeneratedQuiz.class);
                                    terminal = true;
                                    continue;
                                }
                                if ("FAILED".equals(type)) {
                                    terminal = true;
                                    persistStreamEvent(jobId, event);
                                    throw streamFailure(event);
                                }
                                persistStreamEvent(jobId, event);
                            }
                        }
                        if (!terminal || generated == null) {
                            throw new RagServiceException(
                                    "RAG_STREAM_INTERRUPTED",
                                    "Kết nối trạng thái RAG bị gián đoạn.",
                                    true,
                                    Duration.ofMinutes(5),
                                    null,
                                    null);
                        }
                        return generated;
                    });
        } catch (RagServiceException exception) {
            throw exception;
        } catch (Exception exception) {
            if (hasCause(exception, SocketTimeoutException.class)) {
                throw new RagServiceException(
                        "RAG_STREAM_READ_TIMEOUT",
                        "RAG chưa gửi trạng thái mới trước thời hạn chờ của backend.",
                        true,
                        Duration.ofMinutes(5),
                        null,
                        exception);
            }
            throw new RagServiceException(
                    "RAG_STREAM_INTERRUPTED",
                    "Kết nối trạng thái RAG bị gián đoạn.",
                    true,
                    Duration.ofMinutes(5),
                    null,
                    exception);
        }
    }

    private static boolean hasCause(Throwable error, Class<? extends Throwable> type) {
        Throwable current = error;
        while (current != null) {
            if (type.isInstance(current)) return true;
            current = current.getCause();
        }
        return false;
    }

    private void persistStreamEvent(UUID jobId, JsonNode event) {
        if (events == null) return;
        JobEventLevel level;
        try {
            level = JobEventLevel.valueOf(
                    event.path("level").stringValue("INFO"));
        } catch (IllegalArgumentException ignored) {
            level = JobEventLevel.INFO;
        }
        events.record(
                jobId,
                level,
                event.path("type").stringValue("RAG_STATUS"),
                event.path("message").stringValue("RAG đang xử lý yêu cầu."),
                null,
                nullableText(event, "provider"),
                nullableInteger(event, "batchIndex"),
                nullableInteger(event, "partIndex"),
                nullableText(event, "requestId"),
                event);
    }

    private void persistHttpFailure(UUID jobId, RagServiceException failure) {
        if (events == null) return;
        var metadata = mapper.createObjectNode();
        if (failure.details() != null && failure.details().isArray()) {
            metadata.set("details", failure.details().deepCopy());
        }
        events.record(
                jobId,
                JobEventLevel.ERROR,
                failure.code(),
                failure.getMessage(),
                null,
                null,
                null,
                null,
                failure.upstreamRequestId(),
                metadata);
    }

    private RagServiceException streamFailure(JsonNode event) {
        boolean retryable = event.path("retryable").asBoolean(false);
        Integer delay = nullableInteger(event, "retryAfterSeconds");
        return new RagServiceException(
                event.path("errorCode").stringValue("RAG_STREAM_FAILED"),
                event.path("message").stringValue(
                        "Dịch vụ RAG không thể hoàn tất yêu cầu."),
                retryable,
                delay == null ? null : Duration.ofSeconds(delay),
                nullableText(event, "requestId"),
                event.path("details").isArray()
                        ? event.path("details").deepCopy() : null,
                null);
    }

    private RagServiceException decodeStreamingError(
            int status, byte[] bytes, Throwable cause) {
        try {
            JsonNode body = mapper.readTree(
                    new String(bytes, StandardCharsets.UTF_8));
            boolean retryable = body.path("retryable").asBoolean(status >= 500);
            Integer delay = nullableInteger(body, "retryAfterSeconds");
            return new RagServiceException(
                    body.path("code").stringValue("RAG_UNAVAILABLE"),
                    body.path("message").stringValue(
                            "Dịch vụ RAG không thể xử lý yêu cầu."),
                    retryable,
                    delay == null ? null : Duration.ofSeconds(delay),
                    nullableText(body, "requestId"),
                    body.path("details").isArray()
                            ? body.path("details").deepCopy() : null,
                    cause);
        } catch (Exception ignored) {
            return new RagServiceException(
                    "RAG_UNAVAILABLE",
                    "Dịch vụ RAG không thể xử lý yêu cầu.",
                    status >= 500,
                    status >= 500 ? Duration.ofMinutes(5) : null,
                    null,
                    cause);
        }
    }

    private static String nullableText(JsonNode node, String field) {
        String value = node.path(field).stringValue(null);
        return value == null || value.isBlank() ? null : value;
    }

    private static Integer nullableInteger(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isNumber() ? value.asInt() : null;
    }

    private void internal(org.springframework.http.HttpHeaders headers, UUID userId) {
        headers.set("X-Internal-API-Key", properties.internalApiKey());
        headers.set("X-User-Id", userId.toString());
        String trace = MDC.get("traceId"); if (trace != null) headers.set("X-Request-Id", trace);
    }

    private void internalService(org.springframework.http.HttpHeaders headers) {
        headers.set("X-Internal-API-Key", properties.internalApiKey());
        String trace = MDC.get("traceId");
        if (trace != null) headers.set("X-Request-Id", trace);
    }

    private <T> T call(java.util.concurrent.Callable<T> operation) {
        try {
            T result = operation.call();
            if (result == null) throw new IllegalStateException("RAG trả về nội dung rỗng");
            return result;
        } catch (RestClientResponseException exception) {
            String fallbackCode = switch (exception.getStatusCode().value()) {
                case 401, 403 -> "RAG_AUTHENTICATION_FAILED";
                case 404 -> "RAG_ENDPOINT_NOT_FOUND";
                case 429 -> "RAG_RATE_LIMITED";
                case 422 -> "RAG_CONTEXT_INSUFFICIENT";
                case 502 -> "GROUNDED_QUIZ_INVALID";
                default -> "RAG_INDEXING_FAILED";
            };
            boolean fallbackRetryable = exception.getStatusCode().value() == 429 || exception.getStatusCode().is5xxServerError();
            String code = fallbackCode, message = "Dịch vụ RAG không thể xử lý yêu cầu.";
            boolean retryable = fallbackRetryable; Duration retryAfter = retryable ? Duration.ofSeconds(5) : null;
            String requestId = exception.getResponseHeaders() == null ? null
                    : exception.getResponseHeaders().getFirst("X-Request-Id");
            JsonNode details = null;
            try {
                var body = mapper.readTree(new String(
                        exception.getResponseBodyAsByteArray(), StandardCharsets.UTF_8));
                if (body.path("details").isArray()) {
                    details = body.path("details").deepCopy();
                }
                code = body.path("code").stringValue(fallbackCode);
                if (exception.getStatusCode().value() == 404
                        && "HTTP_ERROR".equals(code)) {
                    code = "RAG_ENDPOINT_NOT_FOUND";
                }
                if ("GROUNDED_QUIZ_INVALID".equals(code)
                        && body.path("details").isArray()
                        && "INVALID_CITATION_QUOTE".equals(
                        body.path("details").path(0).path("reason").stringValue())) {
                    code = "INVALID_CITATION_QUOTE";
                }
                if ("VALIDATION_ERROR".equals(code)
                        && isCognitiveContractValidation(body.path("details"))) {
                    code = "COGNITIVE_PLAN_INVALID";
                }
                message = body.path("message").stringValue(message);
                retryable = body.path("retryable").asBoolean(fallbackRetryable);
                if (!body.path("retryAfterSeconds").isNull() && body.path("retryAfterSeconds").canConvertToInt())
                    retryAfter = Duration.ofSeconds(body.path("retryAfterSeconds").asInt());
                requestId = body.path("requestId").stringValue(requestId);
            } catch (Exception ignored) { }
            throw new RagServiceException(
                    code, message, retryable, retryAfter, requestId, details, exception);
        } catch (Exception exception) {
            throw new RagServiceException("RAG_UNAVAILABLE", "Không thể kết nối dịch vụ RAG.", true,
                    Duration.ofSeconds(5), null, exception);
        }
    }

    private void requireEnabled() {
        if (!properties.enabled()) throw new RagServiceException("RAG_UNAVAILABLE",
                "Dịch vụ RAG chưa được bật.", false, null, null, null);
    }

    private static boolean isCognitiveContractValidation(tools.jackson.databind.JsonNode details) {
        if (!details.isArray()) return false;
        for (tools.jackson.databind.JsonNode detail : details) {
            String value = (
                    detail.path("field").stringValue("")
                    + " "
                    + detail.path("message").stringValue("")
            ).toLowerCase(Locale.ROOT);
            if (value.contains("difficultyplan")
                    || value.contains("questionplan")
                    || value.contains("cognitivemode")
                    || value.contains("cognitivelevel")) {
                return true;
            }
        }
        return false;
    }

    private MultipartBody multipart(String filename, String contentType, byte[] content) {
        String boundary = "BkQuiz-" + UUID.randomUUID();
        String safeFilename = asciiFilename(filename);
        String encodedFilename = URLEncoder.encode(filename == null ? "document" : filename,
                StandardCharsets.UTF_8).replace("+", "%20");
        String safeContentType = safeContentType(contentType);
        try {
            var output = new ByteArrayOutputStream(content.length + 512);
            output.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.US_ASCII));
            output.write(("Content-Disposition: form-data; name=\"file\"; filename=\"" + safeFilename
                    + "\"; filename*=UTF-8''" + encodedFilename + "\r\n").getBytes(StandardCharsets.US_ASCII));
            output.write(("Content-Type: " + safeContentType + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
            output.write(content);
            output.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.US_ASCII));
            return new MultipartBody("multipart/form-data; boundary=" + boundary, output.toByteArray());
        } catch (IOException exception) {
            throw new IllegalStateException("Không thể tạo multipart request.", exception);
        }
    }

    private String asciiFilename(String filename) {
        String source = filename == null || filename.isBlank() ? "document" : filename;
        StringBuilder safe = new StringBuilder(Math.min(source.length(), 200));
        source.codePoints().limit(200).forEach(codePoint -> {
            if (codePoint >= 0x20 && codePoint <= 0x7e && codePoint != '"' && codePoint != '\\') {
                safe.appendCodePoint(codePoint);
            } else {
                safe.append('_');
            }
        });
        return safe.isEmpty() ? "document" : safe.toString();
    }

    private String safeContentType(String contentType) {
        if (contentType == null || contentType.isBlank() || contentType.contains("\r") || contentType.contains("\n")) {
            return MediaType.APPLICATION_OCTET_STREAM_VALUE;
        }
        try {
            return MediaType.parseMediaType(contentType).toString().toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException exception) {
            return MediaType.APPLICATION_OCTET_STREAM_VALUE;
        }
    }

    private record MultipartBody(String contentType, byte[] content) { }
}
