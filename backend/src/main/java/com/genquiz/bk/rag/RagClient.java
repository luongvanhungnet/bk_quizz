package com.genquiz.bk.rag;

import com.genquiz.bk.config.RagProperties;
import tools.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
public class RagClient {
    private final RagProperties properties;
    private final RestClient client;
    private final ObjectMapper mapper;

    public RagClient(RagProperties properties, ObjectMapper mapper) {
        this.properties = properties;
        this.mapper = mapper;
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

    private void internal(org.springframework.http.HttpHeaders headers, UUID userId) {
        headers.set("X-Internal-API-Key", properties.internalApiKey());
        headers.set("X-User-Id", userId.toString());
        String trace = MDC.get("traceId"); if (trace != null) headers.set("X-Request-Id", trace);
    }

    private <T> T call(java.util.concurrent.Callable<T> operation) {
        try {
            T result = operation.call();
            if (result == null) throw new IllegalStateException("RAG trả về nội dung rỗng");
            return result;
        } catch (RestClientResponseException exception) {
            String fallbackCode = switch (exception.getStatusCode().value()) {
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
            try {
                var body = mapper.readTree(new String(
                        exception.getResponseBodyAsByteArray(), StandardCharsets.UTF_8));
                code = body.path("code").stringValue(fallbackCode);
                if ("GROUNDED_QUIZ_INVALID".equals(code)
                        && body.path("details").isArray()
                        && "INVALID_CITATION_QUOTE".equals(
                        body.path("details").path(0).path("reason").stringValue())) {
                    code = "INVALID_CITATION_QUOTE";
                }
                message = body.path("message").stringValue(message);
                retryable = body.path("retryable").asBoolean(fallbackRetryable);
                if (!body.path("retryAfterSeconds").isNull() && body.path("retryAfterSeconds").canConvertToInt())
                    retryAfter = Duration.ofSeconds(body.path("retryAfterSeconds").asInt());
                requestId = body.path("requestId").stringValue(requestId);
            } catch (Exception ignored) { }
            throw new RagServiceException(code, message, retryable, retryAfter, requestId, exception);
        } catch (Exception exception) {
            throw new RagServiceException("RAG_UNAVAILABLE", "Không thể kết nối dịch vụ RAG.", true,
                    Duration.ofSeconds(5), null, exception);
        }
    }

    private void requireEnabled() {
        if (!properties.enabled()) throw new RagServiceException("RAG_UNAVAILABLE",
                "Dịch vụ RAG chưa được bật.", false, null, null, null);
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
