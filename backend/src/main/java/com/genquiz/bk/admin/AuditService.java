package com.genquiz.bk.admin;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.slf4j.MDC;
import com.genquiz.bk.config.AppProperties;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Map;
import java.util.UUID;

@Service
public class AuditService {
    private final AuditLogRepository repository;
    private final ObjectMapper objectMapper;
    private final byte[] auditSalt;
    private final TransactionTemplate independentTransaction;
    public AuditService(AuditLogRepository repository, ObjectMapper objectMapper, AppProperties properties,
                        PlatformTransactionManager transactionManager) {
        this.repository = repository; this.objectMapper = objectMapper;
        this.auditSalt = properties.security().accessSecret().getBytes(StandardCharsets.UTF_8);
        this.independentTransaction = new TransactionTemplate(transactionManager);
        this.independentTransaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public void recordIndependent(UUID actor, String action, String targetType,
                                  String targetId, Map<String, ?> details) {
        independentTransaction.executeWithoutResult(status -> record(actor, action, targetType, targetId, details));
    }
    public void record(UUID actor, String action, String targetType, String targetId, Map<String, ?> details) {
        try {
            RequestMetadata request = requestMetadata();
            repository.save(new AuditLog(actor, action, targetType, targetId,
                    objectMapper.writeValueAsString(details), request.requestId(),
                    request.ipHash(), request.deviceId()));
        }
        catch (JacksonException exception) { throw new IllegalArgumentException("Không thể ghi audit log.", exception); }
    }

    private RequestMetadata requestMetadata() {
        String requestId = bounded(MDC.get("traceId"), 100);
        if (!(RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attributes)) {
            return new RequestMetadata(requestId, null, null);
        }
        var request = attributes.getRequest();
        String forwarded = request.getHeader("X-Forwarded-For");
        String ip = forwarded == null ? request.getRemoteAddr() : forwarded.split(",", 2)[0].trim();
        return new RequestMetadata(requestId, hash(ip), bounded(request.getHeader("X-Device-Id"), 128));
    }

    private String hash(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(auditSalt);
            return java.util.HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }

    private String bounded(String value, int length) {
        if (value == null || value.isBlank()) return null;
        return value.substring(0, Math.min(length, value.length()));
    }

    private record RequestMetadata(String requestId, String ipHash, String deviceId) {}
}
