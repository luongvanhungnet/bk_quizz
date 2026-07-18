package com.genquiz.bk.admin;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.UUID;

@Service
public class AuditService {
    private final AuditLogRepository repository;
    private final ObjectMapper objectMapper;
    public AuditService(AuditLogRepository repository, ObjectMapper objectMapper) {
        this.repository = repository; this.objectMapper = objectMapper;
    }
    public void record(UUID actor, String action, String targetType, String targetId, Map<String, ?> details) {
        try { repository.save(new AuditLog(actor, action, targetType, targetId, objectMapper.writeValueAsString(details))); }
        catch (JacksonException exception) { throw new IllegalArgumentException("Không thể ghi audit log.", exception); }
    }
}
