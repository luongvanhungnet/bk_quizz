package com.genquiz.bk.admin;

import com.genquiz.bk.security.SecurityOutboxService;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@ConditionalOnProperty(name = "bkquiz.admin-bootstrap.enabled", havingValue = "true")
public class AdminBootstrapRunner implements ApplicationRunner {
    private static final Logger log = LoggerFactory.getLogger(AdminBootstrapRunner.class);
    private final UserRepository users;
    private final JdbcTemplate jdbc;
    private final AuditService audit;
    private final SecurityOutboxService outbox;
    private final String configuredUserId;

    public AdminBootstrapRunner(UserRepository users, JdbcTemplate jdbc, AuditService audit,
                                SecurityOutboxService outbox,
                                @Value("${bkquiz.admin-bootstrap.user-id:}") String configuredUserId) {
        this.users = users;
        this.jdbc = jdbc;
        this.audit = audit;
        this.outbox = outbox;
        this.configuredUserId = configuredUserId;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        jdbc.execute("select pg_advisory_xact_lock(hashtext('bkquiz-initial-owner-bootstrap'))");
        BootstrapState state = jdbc.queryForObject("""
                select completed_at, completed_user_id
                from security_bootstrap_state
                where bootstrap_key = 'INITIAL_OWNER'
                for update
                """, (result, row) -> new BootstrapState(
                result.getObject("completed_at", java.time.OffsetDateTime.class),
                result.getObject("completed_user_id", UUID.class)));
        if (state != null && state.completedAt() != null) {
            log.info("Initial OWNER bootstrap has already been completed; no action was taken.");
            return;
        }

        UUID existingOwner = jdbc.query("""
                select user_id from user_roles where role_code = 'OWNER'
                order by granted_at asc limit 1
                """, result -> result.next() ? result.getObject(1, UUID.class) : null);
        if (existingOwner != null) {
            markCompleted(existingOwner);
            log.info("An OWNER already exists; initial bootstrap has been permanently closed.");
            return;
        }

        UUID targetId;
        try {
            targetId = UUID.fromString(configuredUserId == null ? "" : configuredUserId.trim());
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException(
                    "ADMIN_BOOTSTRAP_USER_ID must identify an existing verified user.", exception);
        }
        User target = users.findByIdAndDeletedAtIsNull(targetId).orElseThrow(() ->
                new IllegalStateException("ADMIN_BOOTSTRAP_USER_ID does not identify an existing user."));
        if (!target.isEmailVerified()) {
            throw new IllegalStateException("The initial OWNER user must have a verified email.");
        }
        if (!target.isActive()) {
            throw new IllegalStateException("The initial OWNER user must be active.");
        }

        jdbc.update("""
                insert into user_roles(user_id, role_code, granted_by)
                values (?, 'USER', ?) on conflict do nothing
                """, targetId, targetId);
        jdbc.update("""
                insert into user_roles(user_id, role_code, granted_by)
                values (?, 'OWNER', ?) on conflict do nothing
                """, targetId, targetId);
        target.setRole(Role.ADMIN);
        markCompleted(targetId);
        audit.record(targetId, "OWNER_BOOTSTRAPPED", "USER", targetId.toString(), Map.of());
        outbox.append(targetId, "OWNER_BOOTSTRAPPED", "initial-owner-bootstrap",
                Map.of("userId", targetId.toString()));
        log.info("Initial OWNER bootstrap completed for userId={}", targetId);
    }

    private void markCompleted(UUID userId) {
        jdbc.update("""
                update security_bootstrap_state
                set completed_at = ?, completed_user_id = ?
                where bootstrap_key = 'INITIAL_OWNER' and completed_at is null
                """, Instant.now(), userId);
    }

    private record BootstrapState(java.time.OffsetDateTime completedAt, UUID completedUserId) {}
}
