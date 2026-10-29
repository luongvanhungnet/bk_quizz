package com.genquiz.bk.security;

import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Service
public class SecurityOutboxService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public SecurityOutboxService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    public void append(UUID aggregateId, String eventType, String dedupKey, Map<String, ?> payload) {
        try {
            jdbc.update("""
                    insert into outbox_events(
                        id, aggregate_type, aggregate_id, event_type, dedup_key, payload)
                    values (?, 'USER_SECURITY', ?, ?, ?, cast(? as jsonb))
                    on conflict (dedup_key) do nothing
                    """, UUID.randomUUID(), aggregateId, eventType, dedupKey,
                    mapper.writeValueAsString(payload));
        } catch (JacksonException exception) {
            throw new IllegalArgumentException("Không thể tạo security outbox event.", exception);
        }
    }
}
