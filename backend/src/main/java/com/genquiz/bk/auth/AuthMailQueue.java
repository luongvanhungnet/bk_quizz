package com.genquiz.bk.auth;

import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobService;
import com.genquiz.bk.job.JobType;
import java.util.UUID;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Service
public class AuthMailQueue {
    private final JobService jobs;
    private final SensitivePayloadCipher cipher;
    private final ObjectMapper objectMapper;

    public AuthMailQueue(JobService jobs, SensitivePayloadCipher cipher, ObjectMapper objectMapper) {
        this.jobs = jobs; this.cipher = cipher; this.objectMapper = objectMapper;
    }

    public Job enqueue(AuthMailEvent.Type type, UUID userId, UUID resourceId,
                       String recipient, String username, String rawToken) {
        try {
            String payload = objectMapper.writeValueAsString(
                    new AuthMailPayload(type, recipient, username, cipher.encrypt(rawToken)));
            String key = "auth-email:" + type.name().toLowerCase() + ":" + resourceId;
            return jobs.enqueue(JobType.AUTH_EMAIL, userId, resourceId, payload, key, 5);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Không thể tạo tác vụ gửi email.", exception);
        }
    }
}
