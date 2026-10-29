package com.genquiz.bk.security;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthorizationService {
    private final JdbcTemplate jdbc;

    public AuthorizationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public AuthorizationSnapshot snapshot(UUID userId) {
        Set<String> roles = new LinkedHashSet<>();
        Set<String> permissions = new LinkedHashSet<>();
        jdbc.query("""
                select ur.role_code, rp.permission_code
                from user_roles ur
                left join role_permissions rp on rp.role_code = ur.role_code
                where ur.user_id = ?
                order by ur.role_code, rp.permission_code
                """, (org.springframework.jdbc.core.RowCallbackHandler)
                result -> collect(result, roles, permissions), userId);
        // Rollout safety for a user created in the same transaction or by an old client.
        if (roles.isEmpty()) roles.add(AdministrativeRole.USER.name());
        return new AuthorizationSnapshot(Set.copyOf(roles), Set.copyOf(permissions));
    }

    @Transactional
    public void assignBaselineUser(UUID userId) {
        jdbc.update("""
                insert into user_roles(user_id, role_code)
                values (?, 'USER') on conflict do nothing
                """, userId);
    }

    @Transactional(readOnly = true)
    public boolean hasRole(UUID userId, AdministrativeRole role) {
        Integer count = jdbc.queryForObject(
                "select count(*) from user_roles where user_id = ? and role_code = ?",
                Integer.class, userId, role.name());
        return count != null && count > 0;
    }

    private void collect(ResultSet result, Set<String> roles, Set<String> permissions) throws SQLException {
        roles.add(result.getString("role_code"));
        String permission = result.getString("permission_code");
        if (permission != null) permissions.add(permission);
    }

    public record AuthorizationSnapshot(Set<String> roles, Set<String> permissions) {
        public Set<String> authorities() {
            Set<String> values = new LinkedHashSet<>(permissions);
            roles.forEach(role -> values.add("ROLE_" + role));
            return Set.copyOf(values);
        }
    }
}
