package com.genquiz.bk.admin;

import com.genquiz.bk.attempt.AttemptRepository;
import com.genquiz.bk.abuse.AiAbuseProtectionService;
import com.genquiz.bk.auth.RefreshSessionRepository;
import com.genquiz.bk.classroom.ClassroomRepository;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.job.JobRepository;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.security.CurrentUser;
import com.genquiz.bk.security.SecurityOutboxService;
import com.genquiz.bk.storage.StoredFile;
import com.genquiz.bk.storage.StoredFileRepository;
import com.genquiz.bk.topic.TopicRepository;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import com.genquiz.bk.user.dto.UserDto;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;
import com.genquiz.bk.job.Job;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Set;

@Service
public class AdminService {
    private final UserRepository users;
    private final AuditLogRepository auditLogs;
    private final AuditService audit;
    private final CurrentUser current;
    private final TopicRepository topics;
    private final QuizRepository quizzes;
    private final ClassroomRepository classrooms;
    private final AttemptRepository attempts;
    private final JobRepository jobs;
    private final StoredFileRepository files;
    private final RefreshSessionRepository sessions;
    private final JdbcTemplate jdbc;
    private final SecurityOutboxService outbox;
    private AiAbuseProtectionService aiAbuseProtection;

    public AdminService(UserRepository users, AuditLogRepository auditLogs, AuditService audit, CurrentUser current,
                        TopicRepository topics, QuizRepository quizzes, ClassroomRepository classrooms,
                        AttemptRepository attempts, JobRepository jobs, StoredFileRepository files,
                        RefreshSessionRepository sessions, JdbcTemplate jdbc, SecurityOutboxService outbox) {
        this.users=users;this.auditLogs=auditLogs;this.audit=audit;this.current=current;this.topics=topics;
        this.quizzes=quizzes;this.classrooms=classrooms;this.attempts=attempts;this.jobs=jobs;this.files=files;this.sessions=sessions;this.jdbc=jdbc;this.outbox=outbox;
    }

    @Autowired(required = false)
    void setAiAbuseProtection(AiAbuseProtectionService value) {
        this.aiAbuseProtection = value;
    }

    @Transactional(readOnly = true)
    public AdminDtos.Summary summary() {
        return new AdminDtos.Summary(users.count(), topics.count(), quizzes.count(), classrooms.count(), attempts.count(),
                jobs.count(), files.count(), files.totalReadyBytes());
    }

    @Transactional(readOnly = true)
    public Page<UserDto> users(String search, int page, int limit) {
        return users.search(search == null ? "" : search.trim(),
                PageRequest.of(page - 1, limit, Sort.by(Sort.Direction.DESC, "createdAt"))).map(UserDto::from);
    }

    @Transactional(readOnly = true)
    public UserDto user(UUID id) { return UserDto.from(find(id)); }

    @Transactional(readOnly = true)
    public AdminDtos.UserInvestigation investigation(UUID id) {
        User user=find(id);
        Map<String,Object> reputation=jdbc.queryForMap("""
                select coalesce(r.trust_score,20) trust_score,coalesce(r.risk_score,0) risk_score,
                       coalesce(r.service_level,'CAUTION') service_level,r.daily_quota_override,
                       r.daily_cost_budget_override
                from users u left join account_reputations r on r.user_id=u.id where u.id=?
                """,id);
        Set<String> roles=new java.util.LinkedHashSet<>(jdbc.queryForList("select role_code from user_roles where user_id=? order by role_code",String.class,id));
        LocalDate today=LocalDate.now(ZoneOffset.UTC);
        Map<String,Object> usage=jdbc.queryForMap("""
                select coalesce(sum(ai_request_count),0) requests,coalesce(sum(ai_cost),0) cost
                from daily_user_metrics where user_id=? and metric_date=?
                """,id,today);
        Integer quota=reputation.get("daily_quota_override") instanceof Number n?n.intValue():null;
        BigDecimal budget=reputation.get("daily_cost_budget_override") instanceof BigDecimal b?b:null;
        return new AdminDtos.UserInvestigation(
                new AdminDtos.UserDtoSafe(user.getId(),user.getUsername(),user.getEmail(),user.getRole().name(),user.isActive(),user.isEmailVerified(),user.getCreatedAt()),
                roles,((Number)reputation.get("trust_score")).intValue(),((Number)reputation.get("risk_score")).doubleValue(),
                String.valueOf(reputation.get("service_level")),quota,budget,((Number)usage.get("requests")).longValue(),
                (BigDecimal)usage.get("cost"),
                jdbc.queryForList("select action,target_type,target_id,created_at,request_id from audit_logs where actor_user_id=? or (target_type='USER' and target_id=?) order by created_at desc limit 50",id,id),
                jdbc.queryForList("select event_type,severity,risk_delta,created_at from risk_events where user_id=? order by created_at desc limit 50",id),
                jdbc.queryForList("select id,event_type,occurred_at,properties from product_events where user_id=? order by occurred_at desc limit 50",id));
    }

    @Transactional
    public void adjustQuota(UUID userId, AdminDtos.QuotaAdjustment request) {
        User actor=current.require(); find(userId);
        jdbc.update("insert into account_reputations(user_id) values(?) on conflict(user_id) do nothing",userId);
        jdbc.update("update account_reputations set daily_quota_override=?,daily_cost_budget_override=?,version=version+1 where user_id=?",
                request.dailyQuota(),request.dailyCostBudget(),userId);
        audit.record(actor.getId(),"USER_QUOTA_ADJUSTED","USER",userId.toString(),Map.of(
                "dailyQuota",request.dailyQuota()==null?"default":request.dailyQuota().toString(),
                "dailyCostBudget",request.dailyCostBudget()==null?"default":request.dailyCostBudget().toPlainString()));
    }

    @Transactional
    public UserDto ban(UUID userId) {
        User actor=current.require(); User target=find(userId);
        if(target.getId().equals(actor.getId())) throw new ApiException(HttpStatus.BAD_REQUEST,"CANNOT_BAN_SELF","Không thể tự khóa tài khoản.");
        target.setActive(false); sessions.revokeAllForUser(userId,Instant.now());
        jdbc.update("insert into account_reputations(user_id) values(?) on conflict(user_id) do nothing",userId);
        jdbc.update("update account_reputations set service_level_override='BLOCKED',version=version+1 where user_id=?",userId);
        audit.record(actor.getId(),"USER_BANNED","USER",userId.toString(),Map.of());
        outbox.append(userId,"USER_BANNED","USER_BANNED:"+userId+":"+UUID.randomUUID(),Map.of("actorUserId",actor.getId().toString()));
        return UserDto.from(target);
    }

    @Transactional
    public UserDto restore(UUID userId) {
        User actor=current.require(); User target=find(userId); target.setActive(true);
        jdbc.update("update account_reputations set service_level_override=null,version=version+1 where user_id=?",userId);
        audit.record(actor.getId(),"USER_RESTORED","USER",userId.toString(),Map.of());
        outbox.append(userId,"USER_RESTORED","USER_RESTORED:"+userId+":"+UUID.randomUUID(),Map.of("actorUserId",actor.getId().toString()));
        return UserDto.from(target);
    }

    @Transactional
    public UserDto changeRole(UUID userId, Role role) {
        User actor = current.require();
        User target = find(userId);
        if (role == Role.ADMIN) throw new ApiException(HttpStatus.BAD_REQUEST, "ADMIN_PROMOTION_FORBIDDEN", "Không thể cấp quyền Admin qua API.");
        if (target.getRole() == Role.ADMIN) throw new ApiException(HttpStatus.BAD_REQUEST, "ADMIN_ROLE_IMMUTABLE", "Không thể thay đổi quyền của Admin bootstrap.");
        if (role == Role.TEACHER && !target.isEmailVerified()) throw new ApiException(HttpStatus.BAD_REQUEST, "EMAIL_NOT_VERIFIED", "Chỉ có thể cấp quyền giáo viên cho email đã xác minh.");
        Role previous = target.getRole();
        target.setRole(role);
        sessions.revokeAllForUser(target.getId(), Instant.now());
        audit.record(actor.getId(), "USER_ROLE_CHANGED", "USER", target.getId().toString(), Map.of("from", previous.name(), "to", role.name()));
        return UserDto.from(target);
    }

    @Transactional
    public UserDto changeStatus(UUID userId, boolean active) {
        User actor = current.require(); User target = find(userId);
        if (target.getId().equals(actor.getId()) && !active) throw new ApiException(HttpStatus.BAD_REQUEST, "CANNOT_DISABLE_SELF", "Admin không thể tự khóa chính mình.");
        if (target.getRole() == Role.ADMIN && !active) throw new ApiException(HttpStatus.BAD_REQUEST, "ADMIN_STATUS_IMMUTABLE", "Không thể khóa tài khoản Admin bootstrap.");
        target.setActive(active);
        if (!active) sessions.revokeAllForUser(target.getId(), Instant.now());
        String eventType = active ? "USER_ACTIVATED" : "USER_SUSPENDED";
        audit.record(actor.getId(), eventType, "USER", target.getId().toString(), Map.of());
        outbox.append(target.getId(), eventType,
                eventType + ":" + target.getId() + ":" + UUID.randomUUID(), Map.of(
                "actorUserId", actor.getId().toString(),
                "targetUserId", target.getId().toString(),
                "active", active
        ));
        return UserDto.from(target);
    }

    @Transactional
    public void revokeSessions(UUID userId) {
        User actor=current.require(); User target=find(userId);
        sessions.revokeAllForUser(target.getId(), Instant.now());
        audit.record(actor.getId(), "USER_SESSIONS_REVOKED", "USER", target.getId().toString(), Map.of());
    }

    @Transactional(readOnly = true)
    public Page<StoredFile> files(String search, StoredFile.Status status, int page, int limit) {
        return files.search(search == null ? "" : search.trim(), status, PageRequest.of(page - 1, limit));
    }

    @Transactional(readOnly = true)
    public Page<Job> jobs(int page, int limit) { return jobs.findAll(PageRequest.of(page - 1, limit, Sort.by(Sort.Direction.DESC,"createdAt"))); }

    @Transactional
    public Job retryJob(UUID id) { Job job=jobs.findById(id).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"JOB_NOT_FOUND","Không tìm thấy job."));try{job.retryByAdmin(Instant.now());if(aiAbuseProtection!=null&&job.getType()==com.genquiz.bk.job.JobType.QUIZ_GENERATION)job.attachAiAdmission(aiAbuseProtection.admit(job.getSubjectUserId(),"quiz_generation_admin_retry",job.getPayload()));}catch(IllegalStateException e){throw new ApiException(HttpStatus.CONFLICT,"JOB_NOT_RETRYABLE",e.getMessage());}audit.record(current.id(),"JOB_RETRIED","JOB",id.toString(),Map.of());return job; }

    @Transactional
    public Job cancelJob(UUID id) { Job job=jobs.findById(id).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"JOB_NOT_FOUND","Không tìm thấy job."));try{job.cancelByAdmin(Instant.now());}catch(IllegalStateException e){throw new ApiException(HttpStatus.CONFLICT,"JOB_NOT_CANCELLABLE",e.getMessage());}if(aiAbuseProtection!=null)aiAbuseProtection.release(job);audit.record(current.id(),"JOB_CANCELLED","JOB",id.toString(),Map.of());return job; }

    @Transactional(readOnly = true)
    public java.util.List<java.util.Map<String,Object>> content(String type) {
        String table=switch(type.toLowerCase()){case "topics"->"topics";case "quizzes"->"quizzes";case "classrooms"->"classrooms";default->throw new ApiException(HttpStatus.BAD_REQUEST,"INVALID_CONTENT_TYPE","Loại nội dung không hợp lệ.");};
        String aiValidation = table.equals("quizzes")
                ? ", ai_validation_status, jsonb_array_length(ai_validation_warnings) as ai_validation_warning_count"
                : "";
        return jdbc.queryForList("select id, owner_id, "+(table.equals("quizzes")?"title":"name".replace("name",table.equals("topics")?"title":"name"))+" as title, moderation_status, moderation_reason"+aiValidation+", created_at from "+table+" order by created_at desc limit 100");
    }

    @Transactional
    public void moderate(String type, UUID id, boolean hidden, String reason) {
        String table=switch(type.toLowerCase()){case "topics"->"topics";case "quizzes"->"quizzes";case "classrooms"->"classrooms";default->throw new ApiException(HttpStatus.BAD_REQUEST,"INVALID_CONTENT_TYPE","Loại nội dung không hợp lệ.");};
        int changed=jdbc.update("update "+table+" set moderation_status=?, moderated_by=?, moderated_at=?, moderation_reason=? where id=?",hidden?"HIDDEN":"ACTIVE",current.id(),Instant.now(),hidden?reason:null,id);
        if(changed==0)throw new ApiException(HttpStatus.NOT_FOUND,"CONTENT_NOT_FOUND","Không tìm thấy nội dung.");
        audit.record(current.id(),hidden?"CONTENT_HIDDEN":"CONTENT_RESTORED",type.toUpperCase(),id.toString(),Map.of("reason",reason==null?"":reason));
    }

    @Transactional
    public StoredFile fileStatus(UUID id, StoredFile.Status status) {
        User actor=current.require();
        StoredFile file=files.findById(id).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND,"FILE_NOT_FOUND","Không tìm thấy file."));
        if (status == StoredFile.Status.QUARANTINED) file.quarantine();
        else if (status == StoredFile.Status.READY) file.restore();
        else if (status == StoredFile.Status.DELETED) file.softDelete();
        else throw new ApiException(HttpStatus.BAD_REQUEST,"INVALID_FILE_STATUS","Trạng thái file không hợp lệ.");
        audit.record(actor.getId(),"FILE_STATUS_CHANGED","STORED_FILE",id.toString(),Map.of("status",status.name()));
        return file;
    }

    @Transactional(readOnly = true)
    public Page<AdminDtos.AuditDto> audit(int page, int limit) {
        return auditLogs.findAllByOrderByCreatedAtDesc(PageRequest.of(page - 1, limit)).map(AdminDtos.AuditDto::from);
    }

    @Transactional(readOnly = true)
    public Page<AdminDtos.AuditDto> audit(Instant dateFrom, Instant dateTo, String eventType,
                                          UUID actorId, String targetType, String targetId,
                                          int page, int limit) {
        org.springframework.data.jpa.domain.Specification<AuditLog> spec=(root,query,cb)->cb.conjunction();
        if(dateFrom!=null) spec=spec.and((root,query,cb)->cb.greaterThanOrEqualTo(root.get("createdAt"),dateFrom));
        if(dateTo!=null) spec=spec.and((root,query,cb)->cb.lessThan(root.get("createdAt"),dateTo));
        if(eventType!=null&&!eventType.isBlank()) spec=spec.and((root,query,cb)->cb.equal(root.get("action"),eventType.trim()));
        if(actorId!=null) spec=spec.and((root,query,cb)->cb.equal(root.get("actorUserId"),actorId));
        if(targetType!=null&&!targetType.isBlank()) spec=spec.and((root,query,cb)->cb.equal(root.get("targetType"),targetType.trim()));
        if(targetId!=null&&!targetId.isBlank()) spec=spec.and((root,query,cb)->cb.equal(root.get("targetId"),targetId.trim()));
        return auditLogs.findAll(spec,PageRequest.of(page-1,limit,Sort.by(Sort.Direction.DESC,"createdAt"))).map(AdminDtos.AuditDto::from);
    }

    private User find(UUID id) { return users.findByIdAndDeletedAtIsNull(id).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND,"USER_NOT_FOUND","Không tìm thấy tài khoản.")); }
}
