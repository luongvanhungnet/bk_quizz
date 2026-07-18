package com.genquiz.bk.system;

import com.genquiz.bk.common.api.ApiEnvelope;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class SystemController {
    private final JdbcTemplate jdbc;
    public SystemController(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @GetMapping("/health")
    ResponseEntity<ApiEnvelope<Map<String, Object>>> health() {
        try {
            jdbc.queryForObject("select 1", Integer.class);
            return ResponseEntity.ok(ApiEnvelope.success("Dịch vụ BKQuiz đang hoạt động.", Map.of(
                    "status", "healthy", "database", "connected", "timestamp", Instant.now())));
        } catch (RuntimeException exception) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(ApiEnvelope.success(
                    "Dịch vụ BKQuiz tạm thời không khả dụng.", Map.of(
                            "status", "unhealthy", "database", "disconnected", "timestamp", Instant.now())));
        }
    }
}
