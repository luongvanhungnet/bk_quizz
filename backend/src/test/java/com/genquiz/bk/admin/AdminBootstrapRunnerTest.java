package com.genquiz.bk.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.genquiz.bk.security.SecurityOutboxService;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.sql.ResultSet;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowMapper;

class AdminBootstrapRunnerTest {
    private final UserRepository users = mock(UserRepository.class);
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final AuditService audit = mock(AuditService.class);
    private final SecurityOutboxService outbox = mock(SecurityOutboxService.class);

    @Test
    void verifiedUserCanBeBootstrappedToOwner() throws Exception {
        User target = new User("Owner", "owner@example.com", "hash-value-long-enough");
        target.verifyEmail();
        stubState(null, null);
        stubNoExistingOwner();
        when(users.findByIdAndDeletedAtIsNull(target.getId())).thenReturn(Optional.of(target));

        new AdminBootstrapRunner(users, jdbc, audit, outbox, target.getId().toString())
                .run(new DefaultApplicationArguments(new String[0]));

        assertThat(target.getRole()).isEqualTo(Role.ADMIN);
        verify(jdbc).update(contains("'OWNER'"), eq(target.getId()), eq(target.getId()));
        verify(jdbc).update(contains("security_bootstrap_state"), any(), eq(target.getId()));
        verify(audit).record(eq(target.getId()), eq("OWNER_BOOTSTRAPPED"),
                eq("USER"), eq(target.getId().toString()), any());
        verify(outbox).append(eq(target.getId()), eq("OWNER_BOOTSTRAPPED"),
                eq("initial-owner-bootstrap"), any());
    }

    @Test
    void unverifiedUserCannotBeBootstrapped() throws Exception {
        User target = new User("Owner", "owner@example.com", "hash-value-long-enough");
        stubState(null, null);
        stubNoExistingOwner();
        when(users.findByIdAndDeletedAtIsNull(target.getId())).thenReturn(Optional.of(target));

        assertThatThrownBy(() -> new AdminBootstrapRunner(users, jdbc, audit, outbox,
                target.getId().toString()).run(new DefaultApplicationArguments(new String[0])))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("verified email");
        verify(audit, never()).record(any(), eq("OWNER_BOOTSTRAPPED"), any(), any(), any());
    }

    @Test
    void persistedCompletionPreventsBootstrapAfterRestart() throws Exception {
        UUID completedUser = UUID.randomUUID();
        stubState(OffsetDateTime.now(), completedUser);

        new AdminBootstrapRunner(users, jdbc, audit, outbox, UUID.randomUUID().toString())
                .run(new DefaultApplicationArguments(new String[0]));

        verify(users, never()).findByIdAndDeletedAtIsNull(any());
        verify(audit, never()).record(any(), eq("OWNER_BOOTSTRAPPED"), any(), any(), any());
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private void stubState(OffsetDateTime completedAt, UUID completedUser) throws Exception {
        ResultSet result = mock(ResultSet.class);
        when(result.getObject("completed_at", OffsetDateTime.class)).thenReturn(completedAt);
        when(result.getObject("completed_user_id", UUID.class)).thenReturn(completedUser);
        when(jdbc.queryForObject(contains("security_bootstrap_state"), any(RowMapper.class)))
                .thenAnswer(invocation -> ((RowMapper) invocation.getArgument(1)).mapRow(result, 0));
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private void stubNoExistingOwner() {
        when(jdbc.query(contains("role_code = 'OWNER'"), any(ResultSetExtractor.class))).thenReturn(null);
    }
}
