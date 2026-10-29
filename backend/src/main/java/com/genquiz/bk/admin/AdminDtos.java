package com.genquiz.bk.admin;

import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.util.UUID;
import java.util.Set;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

public final class AdminDtos {
    private AdminDtos() {}
    public enum ManagedRole { STUDENT, TEACHER }
    public record ChangeRoleRequest(@NotNull(message = "Vai trò là bắt buộc.") ManagedRole role) {}
    public record ChangeStatusRequest(@NotNull(message = "Trạng thái là bắt buộc.") Boolean active) {}
    public record UserRoles(UUID userId, Set<String> roles) {}
    public record QuotaAdjustment(@jakarta.validation.constraints.Min(0) Integer dailyQuota,
                                  @jakarta.validation.constraints.DecimalMin("0") BigDecimal dailyCostBudget) {}
    public record UserInvestigation(UserDtoSafe account, Set<String> roles, int trustScore,
                                    double riskScore, String serviceLevel, Integer dailyQuota,
                                    BigDecimal dailyCostBudget, long aiRequestsToday,
                                    BigDecimal aiCostToday, List<Map<String,Object>> recentAuditEvents,
                                    List<Map<String,Object>> recentRiskEvents,
                                    List<Map<String,Object>> recentProductActivity) {}
    public record UserDtoSafe(UUID id,String username,String email,String accountType,boolean active,
                              boolean emailVerified,Instant createdAt) {}
    public record Summary(long users, long topics, long quizzes, long classrooms, long attempts,
                          long jobs, long storedFiles, long storageBytes) {}
    public record AuditDto(UUID id, UUID actorUserId, String action, String targetType,
                           String targetId, String detailsJson, Instant createdAt,
                           String requestId, String ipHash, String deviceId) {
        static AuditDto from(AuditLog log) {
            return new AuditDto(log.getId(), log.getActorUserId(), log.getAction(), log.getTargetType(),
                    log.getTargetId(), log.getDetailsJson(), log.getCreatedAt(),
                    log.getRequestId(), log.getIpHash(), log.getDeviceId());
        }
    }
}
