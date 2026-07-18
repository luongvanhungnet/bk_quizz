package com.genquiz.bk.auth;

import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobHandler;
import com.genquiz.bk.job.JobType;
import java.util.Map;
import java.time.Instant;
import org.springframework.stereotype.Component;
import org.springframework.web.util.HtmlUtils;
import org.springframework.web.util.UriComponentsBuilder;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Component
public class AuthMailJobHandler implements JobHandler {
    private final ObjectMapper objectMapper;
    private final SensitivePayloadCipher cipher;
    private final ResendMailClient resend;
    private final AppProperties properties;
    private final EmailVerificationTokenRepository verificationTokens;

    public AuthMailJobHandler(ObjectMapper objectMapper, SensitivePayloadCipher cipher,
                              ResendMailClient resend, AppProperties properties,
                              EmailVerificationTokenRepository verificationTokens) {
        this.objectMapper = objectMapper; this.cipher = cipher; this.resend = resend; this.properties = properties;
        this.verificationTokens = verificationTokens;
    }

    @Override public JobType type() { return JobType.AUTH_EMAIL; }

    @Override
    public String handle(Job job) throws JacksonException {
        AuthMailPayload payload = objectMapper.readValue(job.getPayload(), AuthMailPayload.class);
        if (payload.type() == AuthMailEvent.Type.VERIFY_EMAIL
                && !verificationTokens.existsByIdAndUsedAtIsNullAndExpiresAtAfter(job.getResourceId(), Instant.now())) {
            return objectMapper.writeValueAsString(Map.of("skipped", true, "reason", "TOKEN_REPLACED_OR_EXPIRED"));
        }
        String token = cipher.decrypt(payload.encryptedToken());
        String path = switch (payload.type()) {
            case VERIFY_EMAIL -> "/verify-email";
            case RESET_PASSWORD -> "/reset-password";
            case CANCEL_DELETION -> "/cancel-deletion";
        };
        String link = UriComponentsBuilder.fromUriString(properties.frontendOrigins().get(0)).path(path)
                .queryParam("token", token).build().toUriString();
        String subject = switch (payload.type()) {
            case VERIFY_EMAIL -> "Xác minh tài khoản BKQuiz";
            case RESET_PASSWORD -> "Đặt lại mật khẩu BKQuiz";
            case CANCEL_DELETION -> "Hủy yêu cầu xóa tài khoản BKQuiz";
        };
        String text = "Xin chào " + payload.username() + ",\n\nVui lòng mở liên kết sau để hoàn tất thao tác:\n"
                + link + "\n\nNếu bạn không yêu cầu thao tác này, hãy bỏ qua email.";
        String html = "<p>Xin chào " + HtmlUtils.htmlEscape(payload.username()) + ",</p>"
                + "<p>Vui lòng mở liên kết sau để hoàn tất thao tác:</p><p><a href=\""
                + HtmlUtils.htmlEscape(link) + "\">Tiếp tục với BKQuiz</a></p>"
                + "<p>Nếu bạn không yêu cầu thao tác này, hãy bỏ qua email.</p>";
        String resendId = resend.send(payload.recipient(), subject, text, html, "auth-email/" + job.getId());
        return objectMapper.writeValueAsString(Map.of("resendEmailId", resendId));
    }
}
