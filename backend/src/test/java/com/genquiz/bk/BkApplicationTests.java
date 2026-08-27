package com.genquiz.bk;

import com.genquiz.bk.job.JobWorker;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "bkquiz.jobs.worker-enabled=false",
        "bkquiz.rate-limit.enabled=false",
        "bkquiz.storage.clamav-enabled=false",
        "spring.ai.model.chat=none"
})
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class BkApplicationTests {
    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>(
            DockerImageName.parse("pgvector/pgvector:pg16").asCompatibleSubstituteFor("postgres"));

    @Autowired
    MockMvc mockMvc;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    ApplicationContext applicationContext;

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.flyway.user", POSTGRES::getUsername);
        registry.add("spring.flyway.password", POSTGRES::getPassword);
    }

    @Test
    void contextLoadsAndFlywaySchemaMatchesEntities() {}

    @Test
    void workerIsNotCreatedWhenDisabled() {
        assertThat(applicationContext.getBeansOfType(JobWorker.class)).isEmpty();
    }

    @Test
    void actuatorReadinessReportsUpWhenDatabaseIsAvailable() throws Exception {
        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void applicationHealthReportsConnectedDatabase() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.database").value("connected"));
    }

    @Test
    void migrationAlignsUserPreferencesWithEntity() {
        Integer studyColumn = jdbc.queryForObject("""
                select count(*) from information_schema.columns
                where table_schema = 'public' and table_name = 'user_preferences'
                  and column_name = 'email_study_reminders'
                """, Integer.class);
        Integer legacyColumn = jdbc.queryForObject("""
                select count(*) from information_schema.columns
                where table_schema = 'public' and table_name = 'user_preferences'
                  and column_name = 'email_assignment_reminders'
                """, Integer.class);

        assertThat(studyColumn).isEqualTo(1);
        assertThat(legacyColumn).isZero();
    }

    @Test
    void migrationAlignsAttemptsWithEntity() {
        assertThat(columnExists("attempts", "assignment_due_at")).isTrue();
        assertThat(columnExists("attempts", "max_score")).isTrue();
        assertThat(columnExists("attempts", "total_questions")).isTrue();
        assertThat(columnExists("attempts", "total_count")).isFalse();
    }

    @Test
    void migrationAddsClassroomCollaborationSchema() {
        assertThat(columnExists("classrooms", "join_enabled")).isTrue();
        assertThat(columnExists("classroom_members", "last_read_message_at")).isTrue();
        assertThat(columnExists("assignments", "share_kind")).isTrue();
        assertThat(columnExists("assignments", "show_leaderboard")).isTrue();
        assertThat(columnExists("attempts", "show_score")).isTrue();
        assertThat(columnExists("attempts", "allow_review")).isTrue();
        assertThat(tableExists("classroom_messages")).isTrue();
        assertThat(tableExists("classroom_attachments")).isTrue();
        assertThat(tableExists("classroom_topic_shares")).isTrue();
    }

    @Test
    void migrationAlignsQuizGenerationErrorsWithEntity() {
        assertThat(columnExists("quizzes", "error_code")).isTrue();
        assertThat(columnExists("quizzes", "error_message")).isTrue();
        assertThat(columnExists("quizzes", "generation_error_code")).isFalse();
        assertThat(columnExists("quizzes", "generation_error_message")).isFalse();
    }

    @Test
    void registrationAllowsTeacherButNeverAdmin() throws Exception {
        String teacherEmail = "teacher-" + UUID.randomUUID() + "@example.com";
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"Integration Teacher","email":"%s","password":"StrongPass123","accountType":"TEACHER"}
                                """.formatted(teacherEmail)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.data.user.role").value("TEACHER"));
        assertThat(jdbc.queryForObject("select role from users where email = ?", String.class, teacherEmail))
                .isEqualTo("TEACHER");

        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"Invalid Admin","email":"admin-%s@example.com","password":"StrongPass123","accountType":"ADMIN"}
                                """.formatted(UUID.randomUUID())))
                .andExpect(status().isBadRequest());
    }

    @Test
    void registerPersistsPreferencesVerificationTokenAndRefreshSession() throws Exception {
        String email = "registration-" + UUID.randomUUID() + "@example.com";

        String response = mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Origin", "http://localhost:5173")
                        .content(registerBody(email)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.accessToken").isNotEmpty())
                .andExpect(cookie().exists("bkquiz_refresh"))
                .andExpect(cookie().exists("XSRF-TOKEN"))
                .andReturn().getResponse().getContentAsString();

        String accessToken = objectMapper.readTree(response).get("data").get("accessToken").stringValue();
        mockMvc.perform(get("/api/users/me/dashboard")
                        .header("Authorization", "Bearer " + accessToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.stats.topicCount").value(0))
                .andExpect(jsonPath("$.data.stats.quizCount").value(0))
                .andExpect(jsonPath("$.data.stats.submittedAttemptCount").value(0))
                .andExpect(jsonPath("$.data.stats.averagePercentage").value(0))
                .andExpect(jsonPath("$.data.recentActivities").isEmpty());

        UUID userId = jdbc.queryForObject("select id from users where email = ?", UUID.class, email);
        assertThat(userId).isNotNull();
        assertThat(jdbc.queryForObject("""
                select email_study_reminders from user_preferences where user_id = ?
                """, Boolean.class, userId)).isTrue();
        assertThat(jdbc.queryForObject("select count(*) from email_verification_tokens where user_id = ?",
                Integer.class, userId)).isEqualTo(1);
        assertThat(jdbc.queryForObject("select count(*) from refresh_sessions where user_id = ?",
                Integer.class, userId)).isEqualTo(1);
        assertThat(jdbc.queryForObject("select count(*) from jobs where subject_user_id = ? and type = 'AUTH_EMAIL'",
                Integer.class, userId)).isEqualTo(1);
    }

    @Test
    void duplicateRegistrationReturnsConflictWithoutPartialData() throws Exception {
        String email = "duplicate-" + UUID.randomUUID() + "@example.com";

        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(registerBody(email)))
                .andExpect(status().isCreated());
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(registerBody(email)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errors[0].code").value("EMAIL_ALREADY_EXISTS"));

        assertThat(jdbc.queryForObject("select count(*) from users where email = ?", Integer.class, email))
                .isEqualTo(1);
        assertThat(jdbc.queryForObject("""
                select count(*) from user_preferences p join users u on u.id = p.user_id where u.email = ?
                """, Integer.class, email)).isEqualTo(1);
    }

    @Test
    void verifiedStudentCanUpgradeToTeacherAndReceivesReplacementSession() throws Exception {
        String email = "upgrade-" + UUID.randomUUID() + "@example.com";
        String registration = mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(registerBody(email)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        String accessToken = objectMapper.readTree(registration).get("data").get("accessToken").stringValue();
        jdbc.update("update users set email_verified_at = current_timestamp where email = ?", email);

        mockMvc.perform(post("/api/users/me/account-type")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + accessToken)
                        .content("""
                                {"targetRole":"TEACHER","password":"StrongPass123"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.user.role").value("TEACHER"))
                .andExpect(jsonPath("$.data.accessToken").isNotEmpty())
                .andExpect(cookie().exists("bkquiz_refresh"))
                .andExpect(cookie().exists("XSRF-TOKEN"));

        UUID userId = jdbc.queryForObject("select id from users where email = ?", UUID.class, email);
        assertThat(jdbc.queryForObject("select role from users where id = ?", String.class, userId))
                .isEqualTo("TEACHER");
        assertThat(jdbc.queryForObject("""
                select count(*) from refresh_sessions where user_id = ? and revoked_at is null
                """, Integer.class, userId)).isEqualTo(1);
    }

    @Test
    void verifiedStudentCanJoinClassroomByCode() throws Exception {
        String teacherEmail = "class-teacher-" + UUID.randomUUID() + "@example.com";
        String teacherRegistration = mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"Class Teacher","email":"%s","password":"StrongPass123","accountType":"TEACHER"}
                                """.formatted(teacherEmail)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        String teacherToken = objectMapper.readTree(teacherRegistration).get("data").get("accessToken").stringValue();
        jdbc.update("update users set email_verified_at = current_timestamp where email = ?", teacherEmail);

        String classroomResponse = mockMvc.perform(post("/api/classrooms")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + teacherToken)
                        .content("{\"name\":\"Integration Classroom\",\"description\":\"Join flow\"}"))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        String joinCode = objectMapper.readTree(classroomResponse).get("data").get("joinCode").stringValue();
        String classroomId = objectMapper.readTree(classroomResponse).get("data").get("id").stringValue();

        String studentEmail = "class-student-" + UUID.randomUUID() + "@example.com";
        String studentRegistration = mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(registerBody(studentEmail)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        String studentToken = objectMapper.readTree(studentRegistration).get("data").get("accessToken").stringValue();
        jdbc.update("update users set email_verified_at = current_timestamp where email = ?", studentEmail);

        mockMvc.perform(post("/api/classrooms/join")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + studentToken)
                        .content("{\"joinCode\":\"%s\"}".formatted(joinCode.toLowerCase())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.id").value(classroomId));

        UUID studentId = jdbc.queryForObject("select id from users where email = ?", UUID.class, studentEmail);
        assertThat(jdbc.queryForObject("""
                select count(*) from classroom_members
                where classroom_id = ?::uuid and user_id = ? and status = 'ACTIVE'
                """, Integer.class, classroomId, studentId)).isEqualTo(1);
        assertThat(jdbc.queryForObject("""
                select count(*) from notifications where related_type = 'CLASSROOM' and related_id = ?::uuid
                """, Integer.class, classroomId)).isEqualTo(1);
    }

    private String registerBody(String email) {
        return """
                {"username":"%s","email":"%s","password":"StrongPass123"}
                """.formatted("User-" + Integer.toUnsignedString(email.hashCode()), email);
    }

    private boolean columnExists(String table, String column) {
        Integer count = jdbc.queryForObject("""
                select count(*) from information_schema.columns
                where table_schema = 'public' and table_name = ? and column_name = ?
                """, Integer.class, table, column);
        return count != null && count == 1;
    }


    private boolean tableExists(String table) {
        Integer count = jdbc.queryForObject("""
                select count(*) from information_schema.tables
                where table_schema = 'public' and table_name = ?
                """, Integer.class, table);
        return count != null && count == 1;
    }
}
