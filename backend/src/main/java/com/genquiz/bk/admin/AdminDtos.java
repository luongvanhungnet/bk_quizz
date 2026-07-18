package com.genquiz.bk.admin;

import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.util.UUID;

public final class AdminDtos {
    private AdminDtos() {}
    public enum ManagedRole { STUDENT, TEACHER }
    public record ChangeRoleRequest(@NotNull(message = "Vai trò là bắt buộc.") ManagedRole role) {}
    public record ChangeStatusRequest(@NotNull(message = "Trạng thái là bắt buộc.") Boolean active) {}
    public record Summary(long users, long topics, long quizzes, long classrooms, long attempts,
                          long jobs, long storedFiles, long storageBytes) {}
    public record AuditDto(UUID id, UUID actorUserId, String action, String targetType,
                           String targetId, String detailsJson, Instant createdAt) {
        static AuditDto from(AuditLog log) {
            return new AuditDto(log.getId(), log.getActorUserId(), log.getAction(), log.getTargetType(),
                    log.getTargetId(), log.getDetailsJson(), log.getCreatedAt());
        }
    }
}
