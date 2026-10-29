package com.genquiz.bk.auth;

import com.genquiz.bk.config.MailProperties;
import com.genquiz.bk.config.ResendProperties;
import com.genquiz.bk.job.RetryableJobException;
import java.net.http.HttpClient;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.Locale;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
public class ResendMailClient {
    private final ResendProperties resend;
    private final MailProperties mail;
    private final RestClient client;

    public ResendMailClient(ResendProperties resend, MailProperties mail, RestClient.Builder builder) {
        this.resend = resend; this.mail = mail;
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(resend.connectTimeout())
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(resend.readTimeout());
        this.client = builder.requestFactory(factory).build();
    }

    public String send(String recipient, String subject, String text, String html, String idempotencyKey) {
        requireConfiguration();
        try {
            ResendResponse response = client.post().uri(resend.url())
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + resend.key())
                    .header("Idempotency-Key", idempotencyKey)
                    .header(HttpHeaders.USER_AGENT, "BKQuiz/1.0")
                    .body(Map.of("from", mail.from(), "to", recipient, "subject", subject,
                            "text", text, "html", html))
                    .retrieve().body(ResendResponse.class);
            if (response == null || response.id() == null || response.id().isBlank()) {
                throw new RetryableJobException("Resend trả về phản hồi rỗng.", null);
            }
            return response.id();
        } catch (ResourceAccessException exception) {
            boolean timeout = hasCause(exception, HttpTimeoutException.class);
            throw new ResendConnectivityException(
                    timeout ? "RESEND_CONNECTION_TIMEOUT" : "RESEND_CONNECTION_FAILED",
                    timeout
                            ? "Kết nối từ máy chủ tới Resend đã quá thời gian chờ."
                            : "Máy chủ tạm thời không thể kết nối Resend.",
                    resend.networkRetryDelay(), exception);
        } catch (RestClientResponseException exception) {
            int status = exception.getStatusCode().value();
            if (status == 408 || status == 429 || status >= 500 || status == 409) {
                throw new RetryableJobException("Resend tạm thời từ chối yêu cầu.", retryAfter(exception), exception);
            }
            throw classifyRejectedRequest(exception);
        }
    }

    public void requireConfiguration() {
        if (resend.key() == null || resend.key().isBlank()) {
            throw new ResendDeliveryException("RESEND_CONFIGURATION_MISSING",
                    "Worker gửi email chưa được cấu hình RESEND_API_KEY.");
        }
        if (mail.from() == null || mail.from().isBlank() || !mail.from().contains("@")) {
            throw new ResendDeliveryException("RESEND_SENDER_INVALID",
                    "Địa chỉ người gửi APP_MAIL_FROM không hợp lệ.");
        }
    }

    private ResendDeliveryException classifyRejectedRequest(RestClientResponseException exception) {
        String providerMessage = exception.getResponseBodyAsString();
        String normalized = providerMessage == null ? "" : providerMessage.toLowerCase(Locale.ROOT);
        int status = exception.getStatusCode().value();
        if (status == 401 || normalized.contains("api key is invalid")
                || normalized.contains("invalid_api_key")) {
            return new ResendDeliveryException("RESEND_AUTHENTICATION_FAILED",
                    "Khóa API Resend không hợp lệ hoặc đã bị thu hồi.", exception);
        }
        if (normalized.contains("domain is not verified")
                || normalized.contains("domain") && normalized.contains("not verified")
                || normalized.contains("testing emails")
                || normalized.contains("verify a domain")) {
            return new ResendDeliveryException("RESEND_SENDER_NOT_VERIFIED",
                    "Tên miền trong APP_MAIL_FROM chưa được xác minh trên Resend.", exception);
        }
        return new ResendDeliveryException("RESEND_REQUEST_REJECTED",
                "Resend từ chối địa chỉ người gửi, người nhận hoặc nội dung email.", exception);
    }

    private Duration retryAfter(RestClientResponseException exception) {
        String value = exception.getResponseHeaders() == null ? null
                : exception.getResponseHeaders().getFirst(HttpHeaders.RETRY_AFTER);
        if (value == null) return null;
        try { return Duration.ofSeconds(Math.max(0, Long.parseLong(value))); }
        catch (NumberFormatException ignored) { return null; }
    }

    private boolean hasCause(Throwable error, Class<? extends Throwable> type) {
        Throwable current = error;
        while (current != null) {
            if (type.isInstance(current)) return true;
            current = current.getCause();
        }
        return false;
    }

    private record ResendResponse(String id) {}
}
