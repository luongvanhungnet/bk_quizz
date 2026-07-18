package com.genquiz.bk.auth;

import com.genquiz.bk.config.MailProperties;
import com.genquiz.bk.config.ResendProperties;
import com.genquiz.bk.job.NonRetryableJobException;
import com.genquiz.bk.job.RetryableJobException;
import java.net.http.HttpClient;
import java.time.Duration;
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
        HttpClient httpClient = HttpClient.newBuilder().connectTimeout(resend.connectTimeout()).build();
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
            throw new RetryableJobException("Không thể kết nối Resend.", null, exception);
        } catch (RestClientResponseException exception) {
            int status = exception.getStatusCode().value();
            if (status == 408 || status == 429 || status >= 500 || status == 409) {
                throw new RetryableJobException("Resend tạm thời từ chối yêu cầu.", retryAfter(exception), exception);
            }
            throw new NonRetryableJobException("Resend từ chối cấu hình hoặc nội dung email.", exception);
        }
    }

    public void requireConfiguration() {
        if (resend.key() == null || resend.key().isBlank()) {
            throw new NonRetryableJobException("RESEND_API_KEY là bắt buộc cho worker.");
        }
        if (mail.from() == null || mail.from().isBlank() || !mail.from().contains("@")) {
            throw new NonRetryableJobException("APP_MAIL_FROM không hợp lệ.");
        }
    }

    private Duration retryAfter(RestClientResponseException exception) {
        String value = exception.getResponseHeaders() == null ? null
                : exception.getResponseHeaders().getFirst(HttpHeaders.RETRY_AFTER);
        if (value == null) return null;
        try { return Duration.ofSeconds(Math.max(0, Long.parseLong(value))); }
        catch (NumberFormatException ignored) { return null; }
    }

    private record ResendResponse(String id) {}
}
