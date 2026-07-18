package com.genquiz.bk.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;

import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobType;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class AuthMailJobHandlerTest {
    @Test
    void skipsVerificationEmailWhenTokenWasReplaced() throws Exception {
        ObjectMapper objectMapper = mock(ObjectMapper.class);
        SensitivePayloadCipher cipher = mock(SensitivePayloadCipher.class);
        ResendMailClient resend = mock(ResendMailClient.class);
        AppProperties properties = mock(AppProperties.class);
        EmailVerificationTokenRepository tokens = mock(EmailVerificationTokenRepository.class);
        UUID tokenId = UUID.randomUUID();
        Job job = new Job(JobType.AUTH_EMAIL, UUID.randomUUID(), tokenId, "{}", null, 5, Instant.now());
        AuthMailPayload payload = new AuthMailPayload(AuthMailEvent.Type.VERIFY_EMAIL,
                "student@example.com", "Student", "encrypted");
        when(objectMapper.readValue("{}", AuthMailPayload.class)).thenReturn(payload);
        when(objectMapper.writeValueAsString(org.mockito.ArgumentMatchers.any())).thenReturn("{\"skipped\":true}");
        when(properties.frontendOrigins()).thenReturn(List.of("http://localhost:5173"));
        when(tokens.existsByIdAndUsedAtIsNullAndExpiresAtAfter(
                org.mockito.ArgumentMatchers.eq(tokenId), org.mockito.ArgumentMatchers.any(Instant.class))).thenReturn(false);

        AuthMailJobHandler handler = new AuthMailJobHandler(objectMapper, cipher, resend, properties, tokens);

        assertThat(handler.handle(job)).isEqualTo("{\"skipped\":true}");
        verifyNoInteractions(resend);
    }

    @Test
    void sendsActiveVerificationTokenUsingFrontendOrigin() throws Exception {
        ObjectMapper objectMapper = mock(ObjectMapper.class);
        SensitivePayloadCipher cipher = mock(SensitivePayloadCipher.class);
        ResendMailClient resend = mock(ResendMailClient.class);
        AppProperties properties = mock(AppProperties.class);
        EmailVerificationTokenRepository tokens = mock(EmailVerificationTokenRepository.class);
        UUID tokenId = UUID.randomUUID();
        Job job = new Job(JobType.AUTH_EMAIL, UUID.randomUUID(), tokenId, "{}", null, 5, Instant.now());
        when(objectMapper.readValue("{}", AuthMailPayload.class)).thenReturn(new AuthMailPayload(
                AuthMailEvent.Type.VERIFY_EMAIL, "student@example.com", "Student", "encrypted"));
        when(tokens.existsByIdAndUsedAtIsNullAndExpiresAtAfter(eq(tokenId), any(Instant.class))).thenReturn(true);
        when(cipher.decrypt("encrypted")).thenReturn("raw-token");
        when(properties.frontendOrigins()).thenReturn(List.of("http://localhost:5173"));
        when(resend.send(any(), any(), any(), any(), any())).thenReturn("resend-1");
        when(objectMapper.writeValueAsString(any())).thenReturn("{\"resendEmailId\":\"resend-1\"}");

        AuthMailJobHandler handler = new AuthMailJobHandler(objectMapper, cipher, resend, properties, tokens);

        assertThat(handler.handle(job)).contains("resend-1");
        verify(resend).send(eq("student@example.com"), contains("BKQuiz"),
                contains("verify-email?token=raw-token"), contains("verify-email?token=raw-token"),
                eq("auth-email/" + job.getId()));
    }
}
