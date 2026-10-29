package com.genquiz.bk.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.genquiz.bk.config.MailProperties;
import com.genquiz.bk.config.ResendProperties;
import com.genquiz.bk.job.RetryableJobException;
import com.genquiz.bk.job.NonRetryableJobException;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

class ResendMailClientTest {
    private HttpServer server;

    @AfterEach void stop() { if (server != null) server.stop(0); }

    @Test
    void sendsBearerPayloadAndIdempotencyKey() throws Exception {
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<String> idempotency = new AtomicReference<>();
        AtomicReference<String> body = new AtomicReference<>();
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/emails", exchange -> {
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            idempotency.set(exchange.getRequestHeaders().getFirst("Idempotency-Key"));
            body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] response = "{\"id\":\"email-123\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();

        ResendMailClient client = client("http://localhost:" + server.getAddress().getPort() + "/emails");
        assertThat(client.send("student@example.com", "Verify", "Text", "<p>Text</p>", "auth-email/1"))
                .isEqualTo("email-123");
        assertThat(authorization.get()).isEqualTo("Bearer re_test");
        assertThat(idempotency.get()).isEqualTo("auth-email/1");
        assertThat(body.get()).contains("BKQuiz <no-reply@example.com>", "student@example.com", "html", "text");
    }

    @Test
    void retriesRateLimitUsingRetryAfter() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/emails", exchange -> {
            exchange.getResponseHeaders().add("Retry-After", "7");
            exchange.sendResponseHeaders(429, -1);
            exchange.close();
        });
        server.start();

        assertThatThrownBy(() -> client("http://localhost:" + server.getAddress().getPort() + "/emails")
                .send("student@example.com", "Verify", "Text", "<p>Text</p>", "auth-email/1"))
                .isInstanceOf(RetryableJobException.class)
                .extracting(error -> ((RetryableJobException) error).retryAfter())
                .isEqualTo(Duration.ofSeconds(7));
    }

    @Test
    void retriesConcurrentConflict() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/emails", exchange -> {
            exchange.sendResponseHeaders(409, -1);
            exchange.close();
        });
        server.start();

        assertThatThrownBy(() -> client("http://localhost:" + server.getAddress().getPort() + "/emails")
                .send("student@example.com", "Verify", "Text", "<p>Text</p>", "auth-email/1"))
                .isInstanceOf(RetryableJobException.class);
    }

    @Test
    void doesNotRetryAuthenticationFailure() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/emails", exchange -> {
            exchange.sendResponseHeaders(401, -1);
            exchange.close();
        });
        server.start();

        assertThatThrownBy(() -> client("http://localhost:" + server.getAddress().getPort() + "/emails")
                .send("student@example.com", "Verify", "Text", "<p>Text</p>", "auth-email/1"))
                .isInstanceOf(NonRetryableJobException.class);
    }

    @Test
    void classifiesInvalidApiKeyWithoutExposingProviderResponse() throws Exception {
        server = errorServer(400, "{\"statusCode\":400,\"name\":\"validation_error\","
                + "\"message\":\"API key is invalid\"}");

        assertThatThrownBy(() -> client("http://localhost:" + server.getAddress().getPort() + "/emails")
                .send("student@example.com", "Verify", "Text", "<p>Text</p>", "auth-email/1"))
                .isInstanceOf(ResendDeliveryException.class)
                .satisfies(error -> {
                    ResendDeliveryException resendError = (ResendDeliveryException) error;
                    assertThat(resendError.code()).isEqualTo("RESEND_AUTHENTICATION_FAILED");
                    assertThat(resendError.getMessage()).isEqualTo(
                            "Khóa API Resend không hợp lệ hoặc đã bị thu hồi.");
                    assertThat(resendError.getMessage()).doesNotContain("re_test");
                });
    }

    @Test
    void classifiesUnverifiedSenderDomain() throws Exception {
        server = errorServer(403, "{\"statusCode\":403,\"name\":\"validation_error\","
                + "\"message\":\"The example.com domain is not verified\"}");

        assertThatThrownBy(() -> client("http://localhost:" + server.getAddress().getPort() + "/emails")
                .send("student@example.com", "Verify", "Text", "<p>Text</p>", "auth-email/1"))
                .isInstanceOf(ResendDeliveryException.class)
                .satisfies(error -> assertThat(((ResendDeliveryException) error).code())
                        .isEqualTo("RESEND_SENDER_NOT_VERIFIED"));
    }

    @Test
    void retriesServerFailure() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/emails", exchange -> {
            exchange.sendResponseHeaders(503, -1);
            exchange.close();
        });
        server.start();

        assertThatThrownBy(() -> client("http://localhost:" + server.getAddress().getPort() + "/emails")
                .send("student@example.com", "Verify", "Text", "<p>Text</p>", "auth-email/1"))
                .isInstanceOf(RetryableJobException.class);
    }

    @Test
    void retriesReadTimeout() throws Exception {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/emails", exchange -> {
            try { Thread.sleep(300); } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
            exchange.close();
        });
        server.start();
        ResendMailClient shortTimeoutClient = new ResendMailClient(
                new ResendProperties("re_test", "http://localhost:" + server.getAddress().getPort() + "/emails",
                        Duration.ofSeconds(1), Duration.ofMillis(50), Duration.ofSeconds(30)),
                new MailProperties("BKQuiz <no-reply@example.com>"), RestClient.builder());

        assertThatThrownBy(() -> shortTimeoutClient
                .send("student@example.com", "Verify", "Text", "<p>Text</p>", "auth-email/1"))
                .isInstanceOf(ResendConnectivityException.class)
                .satisfies(error -> {
                    ResendConnectivityException resendError = (ResendConnectivityException) error;
                    assertThat(resendError.code()).isEqualTo("RESEND_CONNECTION_TIMEOUT");
                    assertThat(resendError.retryAfter()).isEqualTo(Duration.ofSeconds(30));
                });
    }

    private ResendMailClient client(String url) {
        return new ResendMailClient(new ResendProperties("re_test", url, Duration.ofSeconds(2),
                Duration.ofSeconds(2), Duration.ofSeconds(30)),
                new MailProperties("BKQuiz <no-reply@example.com>"), RestClient.builder());
    }

    private HttpServer errorServer(int status, String json) throws Exception {
        HttpServer result = HttpServer.create(new InetSocketAddress(0), 0);
        result.createContext("/emails", exchange -> {
            byte[] response = json.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(status, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        result.start();
        return result;
    }
}
