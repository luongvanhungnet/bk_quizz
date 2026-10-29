package com.genquiz.bk.admin;

import com.genquiz.bk.auth.RefreshSessionRepository;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.security.AdministrativeRole;
import com.genquiz.bk.security.AuthorizationService;
import com.genquiz.bk.security.CurrentUser;
import com.genquiz.bk.security.SecurityOutboxService;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AdminRoleService {
    private final JdbcTemplate jdbc;
    private final UserRepository users;
    private final CurrentUser current;
    private final AuthorizationService authorization;
    private final RefreshSessionRepository sessions;
    private final AuditService audit;
    private final SecurityOutboxService outbox;

    public AdminRoleService(JdbcTemplate jdbc, UserRepository users, CurrentUser current,
                            AuthorizationService authorization, RefreshSessionRepository sessions,
                            AuditService audit, SecurityOutboxService outbox) {
        this.jdbc = jdbc;
        this.users = users;
        this.current = current;
        this.authorization = authorization;
        this.sessions = sessions;
        this.audit = audit;
        this.outbox = outbox;
    }

    @Transactional(readOnly = true)
    public Set<String> roles(UUID userId) {
        find(userId);
        return authorization.snapshot(userId).roles();
    }

    @Transactional
    public Set<String> grant(UUID userId, String requestedRole) {
        User actor = requireOwner();
        User target = find(userId);
        AdministrativeRole role = parse(requestedRole);
        rejectOwnerApiMutation(role);
        rejectSelfMutation(actor, target);
        if (role.privileged() && (!target.isEmailVerified() || !target.isActive())) {
            throw new ApiException(HttpStatus.CONFLICT, "PRIVILEGED_ROLE_TARGET_INELIGIBLE",
                    "Chỉ có thể cấp vai trò đặc quyền cho tài khoản đang hoạt động và đã xác minh email.");
        }
        int inserted = jdbc.update("""
                insert into user_roles(user_id, role_code, granted_by)
                values (?, ?, ?) on conflict do nothing
                """, target.getId(), role.name(), actor.getId());
        if (inserted > 0) {
            if (role == AdministrativeRole.ADMIN) target.setRole(Role.ADMIN);
            sessions.revokeAllForUser(target.getId(), Instant.now());
            audit.record(actor.getId(), "ROLE_GRANTED", "USER", target.getId().toString(),
                    Map.of("role", role.name()));
            outbox.append(target.getId(), "ROLE_GRANTED",
                    "role-granted/" + target.getId() + "/" + role + "/" + UUID.randomUUID(),
                    Map.of("userId", target.getId().toString(), "role", role.name()));
        }
        return authorization.snapshot(target.getId()).roles();
    }

    @Transactional
    public Set<String> revoke(UUID userId, String requestedRole) {
        User actor = requireOwner();
        User target = find(userId);
        AdministrativeRole role = parse(requestedRole);
        rejectOwnerApiMutation(role);
        rejectSelfMutation(actor, target);
        if (role == AdministrativeRole.USER) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "BASELINE_ROLE_IMMUTABLE",
                    "Không thể thu hồi vai trò USER cơ sở.");
        }
        int deleted = jdbc.update("delete from user_roles where user_id = ? and role_code = ?",
                target.getId(), role.name());
        if (deleted > 0) {
            if (role == AdministrativeRole.ADMIN && target.getRole() == Role.ADMIN
                    && !authorization.hasRole(target.getId(), AdministrativeRole.OWNER)) {
                target.setRole(Role.STUDENT);
            }
            sessions.revokeAllForUser(target.getId(), Instant.now());
            audit.record(actor.getId(), "ROLE_REVOKED", "USER", target.getId().toString(),
                    Map.of("role", role.name()));
            outbox.append(target.getId(), "ROLE_REVOKED",
                    "role-revoked/" + target.getId() + "/" + role + "/" + UUID.randomUUID(),
                    Map.of("userId", target.getId().toString(), "role", role.name()));
        }
        return authorization.snapshot(target.getId()).roles();
    }

    private User requireOwner() {
        User actor = current.require();
        if (!authorization.hasRole(actor.getId(), AdministrativeRole.OWNER)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "OWNER_REQUIRED",
                    "Chỉ OWNER được quản lý vai trò đặc quyền.");
        }
        return actor;
    }

    private void rejectOwnerApiMutation(AdministrativeRole role) {
        if (role == AdministrativeRole.OWNER) {
            throw new ApiException(HttpStatus.FORBIDDEN, "OWNER_ROLE_API_FORBIDDEN",
                    "Không thể cấp hoặc thu hồi OWNER qua API quản trị thông thường.");
        }
    }

    private void rejectSelfMutation(User actor, User target) {
        if (actor.getId().equals(target.getId())) {
            throw new ApiException(HttpStatus.FORBIDDEN, "SELF_PRIVILEGE_MUTATION_FORBIDDEN",
                    "Không thể thay đổi vai trò đặc quyền của chính mình.");
        }
    }

    private AdministrativeRole parse(String value) {
        try {
            return AdministrativeRole.parse(value);
        } catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "ADMIN_ROLE_INVALID", "Vai trò quản trị không hợp lệ.");
        }
    }

    private User find(UUID id) {
        return users.findByIdAndDeletedAtIsNull(id).orElseThrow(() ->
                new ApiException(HttpStatus.NOT_FOUND, "USER_NOT_FOUND", "Không tìm thấy tài khoản."));
    }
}
