package com.genquiz.bk.classroom;

import com.genquiz.bk.attempt.AssignmentPolicyGateway;
import com.genquiz.bk.attempt.AttemptRepository;
import com.genquiz.bk.attempt.AttemptStatus;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.notification.NotificationService;
import com.genquiz.bk.quiz.Quiz;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.quiz.QuizStatus;
import com.genquiz.bk.security.VerifiedAccountGuard;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@Service
public class AssignmentService implements AssignmentPolicyGateway {
    private final AssignmentRepository assignments;
    private final AssignmentSubmissionRepository submissions;
    private final ClassroomRepository classrooms;
    private final ClassroomMemberRepository members;
    private final QuizRepository quizzes;
    private final AttemptRepository attempts;
    private final NotificationService notifications;
    private final VerifiedAccountGuard verifiedAccounts;
    private final ClassroomMessageRepository messages;
    private final ApplicationEventPublisher events;
    private final UserRepository users;
    private final ClassroomCollaborationService collaboration;

    @Autowired
    public AssignmentService(AssignmentRepository assignments, AssignmentSubmissionRepository submissions,
                             ClassroomRepository classrooms, ClassroomMemberRepository members,
                             QuizRepository quizzes, AttemptRepository attempts, NotificationService notifications,
                             VerifiedAccountGuard verifiedAccounts, ObjectProvider<ClassroomMessageRepository> messages,
                             ApplicationEventPublisher events, ObjectProvider<UserRepository> users,
                             ObjectProvider<ClassroomCollaborationService> collaboration) {
        this.assignments = assignments;
        this.submissions = submissions;
        this.classrooms = classrooms;
        this.members = members;
        this.quizzes = quizzes;
        this.attempts = attempts;
        this.notifications = notifications;
        this.verifiedAccounts = verifiedAccounts;
        this.messages = messages.getIfAvailable();
        this.events = events;
        this.users = users.getIfAvailable();
        this.collaboration = collaboration.getIfAvailable();
    }

    AssignmentService(AssignmentRepository assignments, AssignmentSubmissionRepository submissions,
                      ClassroomRepository classrooms, ClassroomMemberRepository members,
                      QuizRepository quizzes, AttemptRepository attempts, NotificationService notifications) {
        this.assignments = assignments;
        this.submissions = submissions;
        this.classrooms = classrooms;
        this.members = members;
        this.quizzes = quizzes;
        this.attempts = attempts;
        this.notifications = notifications;
        this.verifiedAccounts = null;
        this.messages = null;
        this.events = null;
        this.users = null;
        this.collaboration = null;
    }

    @Transactional
    public ClassroomDtos.AssignmentResponse create(UUID actorId, UUID classroomId,
                                                    ClassroomDtos.AssignmentRequest request) {
        if (verifiedAccounts != null) verifiedAccounts.require(actorId);
        Classroom classroom = requireClassroom(classroomId);
        ClassroomMember creatorMembership = requireMember(classroomId, actorId);
        if (classroom.getStatus() != ClassroomStatus.ACTIVE) throw new ApiException(HttpStatus.CONFLICT,
                "CLASSROOM_ARCHIVED", "Lớp học đã được lưu trữ.");
        Quiz quiz = requireAssignableQuiz(request.quizId(), actorId);
        Assignment assignment;
        try {
            assignment = new Assignment(classroomId, quiz.getId(), actorId, request.title(), request.instructions(),
                    request.opensAt(), request.dueAt(), request.durationMinutes(), request.maxAttempts(),
                    request.answerReleasePolicy(), Instant.now());
            assignment.configureSharing(creatorMembership.isTeacher() ? AssignmentShareKind.TEACHER_ASSIGNMENT
                            : AssignmentShareKind.MEMBER_SHARE,
                    request.showScore(), request.allowReview(), request.shuffleQuestions(),
                    request.shuffleOptions(), request.showLeaderboard());
        } catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_ASSIGNMENT_WINDOW", exception.getMessage());
        }
        return ClassroomDtos.AssignmentResponse.from(assignments.save(assignment));
    }

    @Transactional(readOnly = true)
    public Page<ClassroomDtos.AssignmentResponse> list(UUID actorId, UUID classroomId, int page, int limit) {
        requireClassroom(classroomId);
        requireMember(classroomId, actorId);
        return assignments.findByClassroomIdAndDeletedAtIsNull(classroomId, PageRequest.of(page - 1, limit))
                .map(ClassroomDtos.AssignmentResponse::from);
    }

    @Transactional(readOnly = true)
    public ClassroomDtos.AssignmentResponse get(UUID actorId, UUID assignmentId) {
        Assignment assignment = requireAssignment(assignmentId);
        requireMember(assignment.getClassroomId(), actorId);
        return ClassroomDtos.AssignmentResponse.from(assignment);
    }

    @Transactional
    public ClassroomDtos.AssignmentResponse update(UUID actorId, UUID assignmentId,
                                                    ClassroomDtos.AssignmentUpdateRequest request) {
        Assignment assignment = requireAssignment(assignmentId);
        Classroom classroom = requireClassroom(assignment.getClassroomId());
        requireManagerOrCreator(classroom, assignment, actorId, true);
        try {
            assignment.update(request.title(), request.instructions(), request.opensAt(), request.dueAt(),
                    request.durationMinutes(), request.maxAttempts(), request.answerReleasePolicy(), Instant.now());
            assignment.configureSharing(assignment.getShareKind(), request.showScore(), request.allowReview(),
                    request.shuffleQuestions(), request.shuffleOptions(), request.showLeaderboard());
        } catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_ASSIGNMENT_WINDOW", exception.getMessage());
        } catch (IllegalStateException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "ASSIGNMENT_NOT_EDITABLE", exception.getMessage());
        }
        return ClassroomDtos.AssignmentResponse.from(assignment);
    }

    @Transactional
    public ClassroomDtos.AssignmentResponse publish(UUID actorId, UUID assignmentId) {
        Assignment assignment = requireAssignment(assignmentId);
        Classroom classroom = requireClassroom(assignment.getClassroomId());
        requireManagerOrCreator(classroom, assignment, actorId, true);
        Quiz quiz = quizzes.findByIdAndDeletedAtIsNull(assignment.getQuizId())
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "QUIZ_NOT_FOUND", "Không tìm thấy bài kiểm tra."));
        if (quiz.getStatus() != QuizStatus.PUBLISHED) {
            throw new ApiException(HttpStatus.CONFLICT, "QUIZ_NOT_PUBLISHED",
                    "Bài kiểm tra phải được xuất bản trước khi giao cho lớp.");
        }
        try {
            assignment.publish(Instant.now());
        } catch (IllegalStateException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "ASSIGNMENT_NOT_PUBLISHABLE", exception.getMessage());
        }
        if (messages != null) {
            ClassroomMessage message = messages.save(new ClassroomMessage(classroom.getId(), actorId,
                    ClassroomMessageType.QUIZ_SHARE, null, null,
                    assignment.getId(), Instant.now()));
            ClassroomCollaborationDtos.MessageResponse payload =
                    collaboration == null ? null : collaboration.response(message);
            if (events != null) events.publishEvent(new ClassroomRealtimeEvent(
                    classroom.getId(), "CREATED", payload));
        }
        for (ClassroomMember member : members.findByClassroomIdAndStatusOrderByJoinedAtAsc(
                classroom.getId(), ClassroomMemberStatus.ACTIVE)) {
            if (member.getRole() == ClassroomMemberRole.STUDENT && !member.getUserId().equals(actorId)) {
                notifications.create(member.getUserId(), "ASSIGNMENT_PUBLISHED", "Bạn có bài tập mới",
                        assignment.getTitle() + " đã được giao trong lớp " + classroom.getName() + ".",
                        "ASSIGNMENT", assignment.getId(),
                        Map.of("classroomId", classroom.getId().toString(), "quizId", quiz.getId().toString()),
                        "assignment-published:" + assignment.getId() + ":" + member.getUserId(), true);
            }
        }
        return ClassroomDtos.AssignmentResponse.from(assignment);
    }

    @Transactional
    public ClassroomDtos.AssignmentResponse close(UUID actorId, UUID assignmentId) {
        Assignment assignment = requireAssignment(assignmentId);
        requireManagerOrCreator(requireClassroom(assignment.getClassroomId()), assignment, actorId, false);
        try {
            assignment.close(Instant.now());
        } catch (IllegalStateException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "ASSIGNMENT_NOT_CLOSABLE", exception.getMessage());
        }
        return ClassroomDtos.AssignmentResponse.from(assignment);
    }

    @Transactional
    public void delete(UUID actorId, UUID assignmentId) {
        Assignment assignment = requireAssignment(assignmentId);
        requireManagerOrCreator(requireClassroom(assignment.getClassroomId()), assignment, actorId, true);
        try {
            assignment.softDelete(Instant.now());
        } catch (IllegalStateException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "ASSIGNMENT_NOT_DELETABLE", exception.getMessage());
        }
    }

    @Transactional(readOnly = true)
    public Page<ClassroomDtos.SubmissionResponse> submissions(UUID actorId, UUID assignmentId,
                                                               int page, int limit) {
        Assignment assignment = requireAssignment(assignmentId);
        Classroom classroom = requireClassroom(assignment.getClassroomId());
        Quiz quiz = quizzes.findByIdAndDeletedAtIsNull(assignment.getQuizId()).orElse(null);
        if (!assignment.getCreatedBy().equals(actorId) && (quiz == null || !quiz.isOwnedBy(actorId))) {
            requireTeacher(classroom, actorId, false);
        }
        Page<com.genquiz.bk.attempt.Attempt> result = submissions.findByAssignmentIdOrderByStartedAtDesc(
                assignmentId, PageRequest.of(page - 1, limit));
        Map<UUID,String> usernames = users == null ? Map.of() : users.findAllById(
                result.getContent().stream().map(com.genquiz.bk.attempt.Attempt::getUserId).toList())
                .stream().collect(java.util.stream.Collectors.toMap(User::getId, User::getUsername));
        return result.map(attempt -> ClassroomDtos.SubmissionResponse.from(attempt,
                usernames.getOrDefault(attempt.getUserId(), "Người dùng đã xóa")));
    }

    @Override
    @Transactional(readOnly = true)
    public Policy authorizeStart(UUID assignmentId, UUID quizId, UUID userId, Instant now) {
        Assignment assignment = requireAssignment(assignmentId);
        if (!assignment.getQuizId().equals(quizId)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "ASSIGNMENT_QUIZ_MISMATCH",
                    "Bài tập không thuộc bài kiểm tra đã chọn.");
        }
        Classroom classroom = requireClassroom(assignment.getClassroomId());
        if (classroom.getStatus() != ClassroomStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "CLASSROOM_ARCHIVED", "Lớp học đã được lưu trữ.");
        }
        requireMember(classroom.getId(), userId);
        if (assignment.getStatus() != AssignmentStatus.PUBLISHED) {
            throw new ApiException(HttpStatus.CONFLICT, "ASSIGNMENT_NOT_AVAILABLE", "Bài tập chưa được mở.");
        }
        if (assignment.getOpensAt() != null && now.isBefore(assignment.getOpensAt())) {
            throw new ApiException(HttpStatus.CONFLICT, "ASSIGNMENT_NOT_OPEN", "Chưa đến thời gian mở bài tập.");
        }
        if (assignment.getDueAt() != null && !now.isBefore(assignment.getDueAt())) {
            throw new ApiException(HttpStatus.CONFLICT, "ASSIGNMENT_OVERDUE", "Bài tập đã quá hạn.");
        }
        if (attempts.existsByAssignmentIdAndUserIdAndStatus(assignmentId, userId, AttemptStatus.IN_PROGRESS)) {
            throw new ApiException(HttpStatus.CONFLICT, "ATTEMPT_ALREADY_ACTIVE",
                    "Bạn đang có một lượt làm chưa hoàn tất cho bài tập này.");
        }
        if (attempts.maxAssignmentAttemptNumber(assignmentId, userId) >= assignment.getMaxAttempts()) {
            throw new ApiException(HttpStatus.CONFLICT, "MAX_ATTEMPTS_REACHED",
                    "Bạn đã sử dụng hết số lượt làm cho bài tập này.");
        }
        return new Policy(assignment.getOpensAt(), assignment.getDueAt(), assignment.getDurationMinutes(),
                assignment.getMaxAttempts(), assignment.getAnswerReleasePolicy(), assignment.isShowScore(),
                assignment.isAllowReview(), assignment.isShuffleQuestions(), assignment.isShuffleOptions());
    }

    private Quiz requireAssignableQuiz(UUID quizId, UUID actorId) {
        Quiz quiz = quizzes.findByIdAndDeletedAtIsNull(quizId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "QUIZ_NOT_FOUND", "Không tìm thấy bài kiểm tra."));
        if (!quiz.isOwnedBy(actorId)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "QUIZ_OWNER_REQUIRED",
                    "Chỉ chủ sở hữu bài kiểm tra mới có thể giao bài.");
        }
        if (quiz.getStatus() != QuizStatus.PUBLISHED) {
            throw new ApiException(HttpStatus.CONFLICT, "QUIZ_NOT_PUBLISHED",
                    "Bài kiểm tra phải được xuất bản trước khi tạo bài tập.");
        }
        return quiz;
    }

    private Assignment requireAssignment(UUID assignmentId) {
        return assignments.findByIdAndDeletedAtIsNull(assignmentId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ASSIGNMENT_NOT_FOUND",
                        "Không tìm thấy bài tập."));
    }

    private Classroom requireClassroom(UUID classroomId) {
        return classrooms.findByIdAndDeletedAtIsNull(classroomId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "CLASSROOM_NOT_FOUND",
                        "Không tìm thấy lớp học."));
    }

    private ClassroomMember requireMember(UUID classroomId, UUID userId) {
        return members.findByClassroomIdAndUserId(classroomId, userId)
                .filter(ClassroomMember::isActive)
                .orElseThrow(() -> new ApiException(HttpStatus.FORBIDDEN, "CLASSROOM_ACCESS_DENIED",
                        "Bạn không phải thành viên của lớp học này."));
    }

    private void requireTeacher(Classroom classroom, UUID userId, boolean requireActiveClassroom) {
        if (requireActiveClassroom && classroom.getStatus() != ClassroomStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "CLASSROOM_ARCHIVED", "Lớp học đã được lưu trữ.");
        }
        if (classroom.isOwnedBy(userId)) return;
        if (!requireMember(classroom.getId(), userId).isTeacher()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "CLASSROOM_TEACHER_REQUIRED",
                    "Bạn cần quyền giảng viên trong lớp học.");
        }
    }

    private void requireManagerOrCreator(Classroom classroom, Assignment assignment, UUID userId,
                                         boolean requireActiveClassroom) {
        if (requireActiveClassroom && classroom.getStatus() != ClassroomStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "CLASSROOM_ARCHIVED", "Lớp học đã được lưu trữ.");
        }
        if (assignment.getShareKind() == AssignmentShareKind.MEMBER_SHARE
                && assignment.getCreatedBy().equals(userId)
                && requireMember(classroom.getId(), userId).isActive()) return;
        requireTeacher(classroom, userId, requireActiveClassroom);
    }
}
