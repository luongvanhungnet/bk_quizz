package com.genquiz.bk.classroom;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.notification.NotificationService;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class ClassroomService {
    private static final char[] JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789".toCharArray();
    private static final SecureRandom RANDOM = new SecureRandom();

    private final ClassroomRepository classrooms;
    private final ClassroomMemberRepository members;
    private final UserRepository users;
    private final NotificationService notifications;

    public ClassroomService(ClassroomRepository classrooms, ClassroomMemberRepository members,
                            UserRepository users, NotificationService notifications) {
        this.classrooms = classrooms;
        this.members = members;
        this.users = users;
        this.notifications = notifications;
    }

    @Transactional
    public ClassroomDtos.ClassroomResponse create(UUID actorId, ClassroomDtos.SaveRequest request) {
        User actor = requireVerifiedUser(actorId);
        if (actor.getRole() == Role.STUDENT) {
            throw new ApiException(HttpStatus.FORBIDDEN, "TEACHER_REQUIRED",
                    "Chỉ giảng viên hoặc quản trị viên mới có thể tạo lớp học.");
        }
        Instant now = Instant.now();
        Classroom classroom = classrooms.save(new Classroom(actorId, request.name(), request.description(),
                nextJoinCode(), now));
        members.save(new ClassroomMember(classroom.getId(), actorId, ClassroomMemberRole.TEACHER, now));
        return ClassroomDtos.ClassroomResponse.from(classroom);
    }

    @Transactional(readOnly = true)
    public Page<ClassroomDtos.ClassroomResponse> list(UUID actorId, int page, int limit) {
        return classrooms.findActiveForMember(actorId, PageRequest.of(page - 1, limit))
                .map(ClassroomDtos.ClassroomResponse::from);
    }

    @Transactional(readOnly = true)
    public ClassroomDtos.ClassroomResponse get(UUID actorId, UUID classroomId) {
        Classroom classroom = findClassroom(classroomId);
        requireActiveMembership(classroomId, actorId);
        return ClassroomDtos.ClassroomResponse.from(classroom);
    }

    @Transactional
    public ClassroomDtos.ClassroomResponse update(UUID actorId, UUID classroomId,
                                                   ClassroomDtos.SaveRequest request) {
        Classroom classroom = findClassroom(classroomId);
        requireTeacher(classroom, actorId);
        try {
            classroom.update(request.name(), request.description(), Instant.now());
        } catch (IllegalStateException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "CLASSROOM_ARCHIVED", exception.getMessage());
        }
        return ClassroomDtos.ClassroomResponse.from(classroom);
    }

    @Transactional
    public ClassroomDtos.ClassroomResponse join(UUID actorId, String rawJoinCode) {
        User actor = requireVerifiedUser(actorId);
        String joinCode = rawJoinCode.trim().toUpperCase(Locale.ROOT);
        Classroom classroom = classrooms.findByJoinCodeIgnoreCaseAndDeletedAtIsNull(joinCode)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "JOIN_CODE_NOT_FOUND",
                        "Mã tham gia lớp học không hợp lệ."));
        ensureActive(classroom);
        if (!classroom.isJoinEnabled()) throw new ApiException(HttpStatus.CONFLICT, "CLASSROOM_JOIN_DISABLED",
                "Lớp học hiện không nhận thành viên mới.");
        Instant now = Instant.now();
        ClassroomMember membership = members.findByClassroomIdAndUserId(classroom.getId(), actorId)
                .map(existing -> {
                    if (existing.isActive()) {
                        throw new ApiException(HttpStatus.CONFLICT, "ALREADY_CLASSROOM_MEMBER",
                                "Bạn đã tham gia lớp học này.");
                    }
                    return reactivate(existing, now);
                })
                .orElseGet(() -> new ClassroomMember(classroom.getId(), actorId, ClassroomMemberRole.STUDENT, now));
        members.save(membership);
        notifications.create(classroom.getOwnerId(), "CLASSROOM_MEMBER_JOINED", "Có thành viên mới",
                actor.getUsername() + " đã tham gia lớp " + classroom.getName() + ".",
                "CLASSROOM", classroom.getId(), Map.of("memberId", actorId.toString()),
                "classroom-join:" + membership.getId() + ":" + now.toEpochMilli(), false);
        return ClassroomDtos.ClassroomResponse.from(classroom);
    }

    @Transactional(readOnly = true)
    public ClassroomDtos.JoinPreview preview(String rawCode) {
        Classroom classroom = classrooms.findByJoinCodeIgnoreCaseAndDeletedAtIsNull(rawCode.trim())
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "JOIN_CODE_NOT_FOUND", "Mã lớp không hợp lệ."));
        User owner = users.findById(classroom.getOwnerId()).orElse(null);
        return new ClassroomDtos.JoinPreview(classroom.getId(), classroom.getName(),
                owner == null ? "Giảng viên" : owner.getUsername(),
                members.countByClassroomIdAndStatus(classroom.getId(), ClassroomMemberStatus.ACTIVE),
                classroom.isJoinEnabled() && classroom.getStatus() == ClassroomStatus.ACTIVE);
    }

    @Transactional
    public ClassroomDtos.ClassroomResponse rotateJoinCode(UUID actorId, UUID classroomId) {
        Classroom classroom = findClassroom(classroomId); requireOwner(classroom, actorId);
        classroom.rotateJoinCode(nextJoinCode(), Instant.now());
        return ClassroomDtos.ClassroomResponse.from(classroom);
    }

    @Transactional
    public ClassroomDtos.ClassroomResponse updateJoinSettings(UUID actorId, UUID classroomId, boolean enabled) {
        Classroom classroom = findClassroom(classroomId); requireOwner(classroom, actorId);
        classroom.setJoinEnabled(enabled, Instant.now());
        return ClassroomDtos.ClassroomResponse.from(classroom);
    }

    @Transactional(readOnly = true)
    public List<ClassroomDtos.MemberResponse> listMembers(UUID actorId, UUID classroomId) {
        findClassroom(classroomId);
        requireActiveMembership(classroomId, actorId);
        List<ClassroomMember> active = members.findByClassroomIdAndStatusOrderByJoinedAtAsc(
                classroomId, ClassroomMemberStatus.ACTIVE);
        Map<UUID, User> userById = users.findAllById(active.stream().map(ClassroomMember::getUserId).toList())
                .stream().collect(Collectors.toMap(User::getId, Function.identity()));
        return active.stream().map(member -> {
            User user = userById.get(member.getUserId());
            return new ClassroomDtos.MemberResponse(member.getId(), member.getUserId(),
                    user == null ? "Người dùng" : user.getUsername(), member.getRole(), member.getStatus(),
                    member.getJoinedAt());
        }).toList();
    }

    @Transactional
    public ClassroomDtos.MemberResponse addMember(UUID actorId, UUID classroomId,
                                                   ClassroomDtos.AddMemberRequest request) {
        Classroom classroom = findClassroom(classroomId);
        requireOwner(classroom, actorId);
        ensureActive(classroom);
        User target = requireVerifiedUser(request.userId());
        if (request.role() == ClassroomMemberRole.TEACHER && target.getRole() == Role.STUDENT) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "TEACHER_ROLE_REQUIRED",
                    "Tài khoản phải có vai trò giảng viên trước khi được thêm làm đồng giảng viên.");
        }
        Instant now = Instant.now();
        ClassroomMember member = members.findByClassroomIdAndUserId(classroomId, target.getId())
                .map(existing -> {
                    if (existing.isActive()) {
                        throw new ApiException(HttpStatus.CONFLICT, "ALREADY_CLASSROOM_MEMBER",
                                "Tài khoản đã là thành viên của lớp học.");
                    }
                    existing.reactivate(request.role(), now);
                    return existing;
                })
                .orElseGet(() -> new ClassroomMember(classroomId, target.getId(), request.role(), now));
        members.save(member);
        notifications.create(target.getId(), "CLASSROOM_MEMBER_ADDED", "Bạn đã được thêm vào lớp học",
                "Bạn đã được thêm vào lớp " + classroom.getName() + ".", "CLASSROOM", classroomId,
                Map.of("role", request.role().name()),
                "classroom-add:" + classroomId + ":" + target.getId() + ":" + now.toEpochMilli(), false);
        return new ClassroomDtos.MemberResponse(member.getId(), member.getUserId(), target.getUsername(),
                member.getRole(), member.getStatus(), member.getJoinedAt());
    }

    @Transactional
    public void removeMember(UUID actorId, UUID classroomId, UUID userId) {
        Classroom classroom = findClassroom(classroomId);
        requireOwner(classroom, actorId);
        if (classroom.isOwnedBy(userId)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "CANNOT_REMOVE_OWNER",
                    "Không thể xóa chủ sở hữu khỏi lớp học.");
        }
        ClassroomMember member = requireActiveMembership(classroomId, userId);
        member.remove(Instant.now());
        notifications.create(userId, "CLASSROOM_MEMBER_REMOVED", "Bạn đã bị xóa khỏi lớp học",
                "Bạn không còn là thành viên của lớp " + classroom.getName() + ".", "CLASSROOM", classroomId,
                Map.of(), "classroom-remove:" + member.getId() + ":" + member.getVersion(), false);
    }

    @Transactional
    public void leave(UUID actorId, UUID classroomId) {
        Classroom classroom = findClassroom(classroomId);
        if (classroom.isOwnedBy(actorId)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "OWNER_CANNOT_LEAVE",
                    "Chủ sở hữu không thể rời lớp; hãy lưu trữ lớp học.");
        }
        ClassroomMember member = requireActiveMembership(classroomId, actorId);
        member.leave(Instant.now());
    }

    @Transactional
    public ClassroomDtos.ClassroomResponse archive(UUID actorId, UUID classroomId) {
        Classroom classroom = findClassroom(classroomId);
        requireOwner(classroom, actorId);
        Instant now = Instant.now();
        classroom.archive(now);
        for (ClassroomMember member : members.findByClassroomIdAndStatusOrderByJoinedAtAsc(
                classroomId, ClassroomMemberStatus.ACTIVE)) {
            if (!member.getUserId().equals(actorId)) {
                notifications.create(member.getUserId(), "CLASSROOM_ARCHIVED", "Lớp học đã được lưu trữ",
                        "Lớp " + classroom.getName() + " đã được lưu trữ.", "CLASSROOM", classroomId,
                        Map.of(), "classroom-archived:" + classroomId, false);
            }
        }
        return ClassroomDtos.ClassroomResponse.from(classroom);
    }

    private ClassroomMember reactivate(ClassroomMember member, Instant now) {
        if (member.isActive()) return member;
        member.reactivate(ClassroomMemberRole.STUDENT, now);
        return member;
    }

    private String nextJoinCode() {
        for (int attempt = 0; attempt < 20; attempt++) {
            StringBuilder candidate = new StringBuilder(8);
            for (int index = 0; index < 8; index++) {
                candidate.append(JOIN_CODE_ALPHABET[RANDOM.nextInt(JOIN_CODE_ALPHABET.length)]);
            }
            String value = candidate.toString();
            if (!classrooms.existsByJoinCodeIgnoreCaseAndDeletedAtIsNull(value)) return value;
        }
        throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "JOIN_CODE_UNAVAILABLE",
                "Không thể cấp mã lớp học lúc này, vui lòng thử lại.");
    }

    private User requireVerifiedUser(UUID userId) {
        User user = users.findById(userId)
                .filter(candidate -> candidate.getDeletedAt() == null)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "USER_NOT_FOUND",
                        "Không tìm thấy tài khoản."));
        if (!user.isActive()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "USER_INACTIVE", "Tài khoản đã bị khóa.");
        }
        if (!user.isEmailVerified()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "EMAIL_NOT_VERIFIED",
                    "Bạn cần xác minh email trước khi sử dụng lớp học.");
        }
        return user;
    }

    private Classroom findClassroom(UUID classroomId) {
        return classrooms.findByIdAndDeletedAtIsNull(classroomId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "CLASSROOM_NOT_FOUND",
                        "Không tìm thấy lớp học."));
    }

    private ClassroomMember requireActiveMembership(UUID classroomId, UUID userId) {
        return members.findByClassroomIdAndUserId(classroomId, userId)
                .filter(ClassroomMember::isActive)
                .orElseThrow(() -> new ApiException(HttpStatus.FORBIDDEN, "CLASSROOM_ACCESS_DENIED",
                        "Bạn không phải thành viên của lớp học này."));
    }

    private void requireTeacher(Classroom classroom, UUID actorId) {
        if (classroom.isOwnedBy(actorId)) return;
        ClassroomMember membership = requireActiveMembership(classroom.getId(), actorId);
        if (!membership.isTeacher()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "CLASSROOM_TEACHER_REQUIRED",
                    "Bạn cần quyền giảng viên trong lớp học.");
        }
    }

    private void requireOwner(Classroom classroom, UUID actorId) {
        if (!classroom.isOwnedBy(actorId)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "CLASSROOM_OWNER_REQUIRED",
                    "Chỉ chủ sở hữu lớp học mới có thể thực hiện thao tác này.");
        }
    }

    private void ensureActive(Classroom classroom) {
        try {
            classroom.requireActive();
        } catch (IllegalStateException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "CLASSROOM_ARCHIVED", exception.getMessage());
        }
    }
}
