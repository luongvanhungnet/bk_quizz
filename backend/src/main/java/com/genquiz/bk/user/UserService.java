package com.genquiz.bk.user;

import com.genquiz.bk.admin.AuditService;
import com.genquiz.bk.auth.AuthMailEvent;
import com.genquiz.bk.auth.AuthMailQueue;
import com.genquiz.bk.auth.RefreshSessionRepository;
import com.genquiz.bk.auth.TokenHashService;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.classroom.ClassroomMemberRepository;
import com.genquiz.bk.classroom.ClassroomMemberRole;
import com.genquiz.bk.classroom.ClassroomMemberStatus;
import com.genquiz.bk.classroom.ClassroomRepository;
import com.genquiz.bk.classroom.ClassroomStatus;
import com.genquiz.bk.security.CurrentUser;
import com.genquiz.bk.user.dto.PreferencesDto;
import com.genquiz.bk.user.dto.UpdatePreferencesRequest;
import com.genquiz.bk.user.dto.UpdateProfileRequest;
import com.genquiz.bk.user.dto.UserDto;
import com.genquiz.bk.user.dto.ChangeAccountTypeRequest;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;

@Service
public class UserService {
    private final CurrentUser current;
    private final UserRepository users;
    private final UserPreferencesRepository preferences;
    private final AccountDeletionRequestRepository deletions;
    private final RefreshSessionRepository sessions;
    private final PasswordEncoder passwords;
    private final TokenHashService tokens;
    private final AuthMailQueue mailQueue;
    private final AuditService audit;
    private final ClassroomRepository classrooms;
    private final ClassroomMemberRepository classroomMembers;

    public UserService(CurrentUser current, UserRepository users, UserPreferencesRepository preferences,
                       AccountDeletionRequestRepository deletions, RefreshSessionRepository sessions,
                       PasswordEncoder passwords, TokenHashService tokens,
                       AuthMailQueue mailQueue, AuditService audit,
                       ClassroomRepository classrooms, ClassroomMemberRepository classroomMembers) {
        this.current = current; this.users = users; this.preferences = preferences; this.deletions = deletions;
        this.sessions = sessions; this.passwords = passwords; this.tokens = tokens; this.mailQueue = mailQueue; this.audit = audit;
        this.classrooms = classrooms; this.classroomMembers = classroomMembers;
    }

    @Transactional
    public User changeAccountType(ChangeAccountTypeRequest request) {
        User user = current.require();
        if (user.getRole() == Role.ADMIN) {
            throw new ApiException(HttpStatus.FORBIDDEN, "ADMIN_ROLE_IMMUTABLE", "Tài khoản quản trị không thể tự đổi loại tài khoản.");
        }
        if (!passwords.matches(request.password(), user.getPasswordHash())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "PASSWORD_INCORRECT", "Mật khẩu không chính xác.");
        }
        Role target = request.targetRole() == ChangeAccountTypeRequest.TargetRole.TEACHER ? Role.TEACHER : Role.STUDENT;
        if (target == user.getRole()) return user;
        if (target == Role.TEACHER && !user.isEmailVerified()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "EMAIL_NOT_VERIFIED", "Bạn cần xác minh email trước khi nâng cấp thành giáo viên.");
        }
        if (target == Role.STUDENT && classrooms.existsByOwnerIdAndStatusAndDeletedAtIsNull(user.getId(), ClassroomStatus.ACTIVE)) {
            throw new ApiException(HttpStatus.CONFLICT, "ACTIVE_CLASSROOMS_EXIST", "Hãy lưu trữ tất cả lớp đang sở hữu trước khi chuyển thành sinh viên.");
        }
        Role previous = user.getRole();
        user.setRole(target);
        if (target == Role.STUDENT) {
            classroomMembers.findByUserIdAndStatus(user.getId(), ClassroomMemberStatus.ACTIVE).stream()
                    .filter(member -> member.getRole() == ClassroomMemberRole.TEACHER)
                    .forEach(member -> member.changeRole(ClassroomMemberRole.STUDENT, Instant.now()));
        }
        sessions.revokeAllForUser(user.getId(), Instant.now());
        audit.record(user.getId(), "ACCOUNT_TYPE_CHANGED", "USER", user.getId().toString(),
                Map.of("from", previous.name(), "to", target.name()));
        return user;
    }

    @Transactional
    public UserDto updateProfile(UpdateProfileRequest request) {
        User user = current.require();
        if (request.username() != null) user.setUsername(request.username().trim());
        if (request.bio() != null) user.setBio(blankToNull(request.bio()));
        return UserDto.from(user);
    }

    @Transactional(readOnly = true)
    public PreferencesDto preferences() {
        User user = current.require();
        return PreferencesDto.from(preferences.findById(user.getId()).orElseGet(() -> new UserPreferences(user)));
    }

    @Transactional
    public PreferencesDto updatePreferences(UpdatePreferencesRequest request) {
        User user = current.require();
        UserPreferences value = preferences.findById(user.getId()).orElseGet(() -> new UserPreferences(user));
        if (request.emailStudyReminders() != null) value.setEmailStudyReminders(request.emailStudyReminders());
        if (request.publicProfile() != null) value.setPublicProfile(request.publicProfile());
        if (request.attemptAutosave() != null) value.setAttemptAutosave(request.attemptAutosave());
        return PreferencesDto.from(preferences.save(value));
    }

    @Transactional
    public void requestDeletion(String password) {
        User user = current.require();
        if (!passwords.matches(password, user.getPasswordHash())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "PASSWORD_INCORRECT", "Mật khẩu không chính xác.");
        }
        if (deletions.findFirstByUserIdAndStatus(user.getId(), "PENDING").isPresent()) return;
        String raw = tokens.newSecret();
        AccountDeletionRequest deletion = deletions.save(new AccountDeletionRequest(
                user, tokens.hash(raw), Instant.now().plus(Duration.ofDays(30))));
        user.requestDeletion();
        sessions.revokeAllForUser(user.getId(), Instant.now());
        audit.record(user.getId(), "ACCOUNT_DELETION_REQUESTED", "USER", user.getId().toString(), Map.of());
        mailQueue.enqueue(AuthMailEvent.Type.CANCEL_DELETION, user.getId(), deletion.getId(),
                user.getEmail(), user.getUsername(), raw);
    }

    @Transactional
    public void cancelDeletion(String rawToken) {
        AccountDeletionRequest request = deletions.findByCancelTokenHashAndStatus(tokens.hash(rawToken), "PENDING")
                .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST, "INVALID_DELETION_TOKEN",
                        "Liên kết hủy xóa tài khoản không hợp lệ hoặc đã hết hạn."));
        request.cancel();
        request.getUser().cancelDeletion();
        audit.record(request.getUser().getId(), "ACCOUNT_DELETION_CANCELLED", "USER",
                request.getUser().getId().toString(), Map.of());
    }

    @Scheduled(cron = "0 15 * * * *")
    @Transactional
    public void anonymizeDueAccounts() {
        for (AccountDeletionRequest request : deletions.findDue(Instant.now())) {
            User user = request.getUser();
            user.anonymize();
            request.processed();
            audit.record(user.getId(), "ACCOUNT_ANONYMIZED", "USER", user.getId().toString(), Map.of());
        }
    }

    private String blankToNull(String value) { String trimmed = value.trim(); return trimmed.isEmpty() ? null : trimmed; }
}
