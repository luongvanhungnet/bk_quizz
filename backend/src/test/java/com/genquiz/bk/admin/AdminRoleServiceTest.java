package com.genquiz.bk.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.genquiz.bk.auth.RefreshSessionRepository;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.security.AdministrativeRole;
import com.genquiz.bk.security.AuthorizationService;
import com.genquiz.bk.security.CurrentUser;
import com.genquiz.bk.security.SecurityOutboxService;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class AdminRoleServiceTest {
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final UserRepository users = mock(UserRepository.class);
    private final CurrentUser current = mock(CurrentUser.class);
    private final AuthorizationService authorization = mock(AuthorizationService.class);
    private final RefreshSessionRepository sessions = mock(RefreshSessionRepository.class);
    private final AuditService audit = mock(AuditService.class);
    private final SecurityOutboxService outbox = mock(SecurityOutboxService.class);
    private final AdminRoleService service = new AdminRoleService(
            jdbc, users, current, authorization, sessions, audit, outbox);
    private User actor;
    private User target;

    @BeforeEach
    void setUp() {
        actor = activeVerified("Owner", "owner@example.com");
        actor.setRole(Role.ADMIN);
        target = activeVerified("Target", "target@example.com");
        when(current.require()).thenReturn(actor);
        when(users.findByIdAndDeletedAtIsNull(target.getId())).thenReturn(Optional.of(target));
        when(authorization.snapshot(target.getId())).thenReturn(
                new AuthorizationService.AuthorizationSnapshot(Set.of("USER", "ADMIN"), Set.of()));
    }

    @Test
    void adminWithoutOwnerRoleCannotGrantAdmin() {
        when(authorization.hasRole(actor.getId(), AdministrativeRole.OWNER)).thenReturn(false);

        assertThatThrownBy(() -> service.grant(target.getId(), "ADMIN"))
                .isInstanceOf(ApiException.class)
                .extracting(error -> ((ApiException) error).code())
                .isEqualTo("OWNER_REQUIRED");
        verify(jdbc, never()).update(anyString(), any(Object[].class));
    }

    @Test
    void ownerCanGrantAdminAndCreatesAuditAndOutbox() {
        when(authorization.hasRole(actor.getId(), AdministrativeRole.OWNER)).thenReturn(true);
        when(jdbc.update(anyString(), any(Object[].class))).thenReturn(1);

        Set<String> roles = service.grant(target.getId(), "ADMIN");

        assertThat(roles).contains("ADMIN");
        assertThat(target.getRole()).isEqualTo(Role.ADMIN);
        verify(audit).record(eq(actor.getId()), eq("ROLE_GRANTED"), eq("USER"),
                eq(target.getId().toString()), any());
        verify(outbox).append(eq(target.getId()), eq("ROLE_GRANTED"), anyString(), any());
    }

    @Test
    void ownerCannotBeCreatedThroughNormalRoleApi() {
        when(authorization.hasRole(actor.getId(), AdministrativeRole.OWNER)).thenReturn(true);

        assertThatThrownBy(() -> service.grant(target.getId(), "OWNER"))
                .isInstanceOf(ApiException.class)
                .extracting(error -> ((ApiException) error).code())
                .isEqualTo("OWNER_ROLE_API_FORBIDDEN");
    }

    @Test
    void ownerCannotMutateOwnPrivileges() {
        when(users.findByIdAndDeletedAtIsNull(actor.getId())).thenReturn(Optional.of(actor));
        when(authorization.hasRole(actor.getId(), AdministrativeRole.OWNER)).thenReturn(true);

        assertThatThrownBy(() -> service.revoke(actor.getId(), "ADMIN"))
                .isInstanceOf(ApiException.class)
                .extracting(error -> ((ApiException) error).code())
                .isEqualTo("SELF_PRIVILEGE_MUTATION_FORBIDDEN");
    }

    private User activeVerified(String name, String email) {
        User user = new User(name, email, "hashed-password-value-value");
        user.verifyEmail();
        return user;
    }
}
