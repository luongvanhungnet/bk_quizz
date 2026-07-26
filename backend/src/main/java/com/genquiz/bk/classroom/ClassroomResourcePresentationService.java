package com.genquiz.bk.classroom;

import com.genquiz.bk.common.ModerationStatus;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.quiz.QuestionRepository;
import com.genquiz.bk.quiz.Quiz;
import com.genquiz.bk.quiz.QuizDtos;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.quiz.QuizStatus;
import com.genquiz.bk.topic.Topic;
import com.genquiz.bk.topic.TopicDtos;
import com.genquiz.bk.topic.TopicRepository;
import com.genquiz.bk.topic.Visibility;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ClassroomResourcePresentationService {
    private final ClassroomMemberRepository members;
    private final ClassroomTopicShareRepository shares;
    private final AssignmentRepository assignments;
    private final TopicRepository topics;
    private final QuizRepository quizzes;
    private final QuestionRepository questions;
    private final UserRepository users;

    public ClassroomResourcePresentationService(
            ClassroomMemberRepository members,
            ClassroomTopicShareRepository shares,
            AssignmentRepository assignments,
            TopicRepository topics,
            QuizRepository quizzes,
            QuestionRepository questions,
            UserRepository users) {
        this.members = members;
        this.shares = shares;
        this.assignments = assignments;
        this.topics = topics;
        this.quizzes = quizzes;
        this.questions = questions;
        this.users = users;
    }

    @Transactional(readOnly = true)
    public Map<UUID, ClassroomCollaborationDtos.ResourcePreview> previews(
            Collection<ClassroomMessage> messages) {
        if (messages.isEmpty()) return Map.of();
        Set<UUID> shareIds = messages.stream().map(ClassroomMessage::getTopicShareId)
                .filter(java.util.Objects::nonNull).collect(Collectors.toSet());
        Set<UUID> assignmentIds = messages.stream().map(ClassroomMessage::getAssignmentId)
                .filter(java.util.Objects::nonNull).collect(Collectors.toSet());
        Map<UUID, ClassroomTopicShare> shareById = byId(
                shares.findAllById(shareIds), ClassroomTopicShare::getId);
        Map<UUID, Assignment> assignmentById = byId(
                assignments.findAllById(assignmentIds), Assignment::getId);
        Map<UUID, Topic> topicById = byId(
                topics.findAllById(shareById.values().stream()
                        .map(ClassroomTopicShare::getTopicId).collect(Collectors.toSet())),
                Topic::getId);
        Map<UUID, Quiz> quizById = byId(
                quizzes.findAllById(assignmentById.values().stream()
                        .map(Assignment::getQuizId).collect(Collectors.toSet())),
                Quiz::getId);
        Set<UUID> ownerIds = new HashSet<>();
        topicById.values().forEach(topic -> ownerIds.add(topic.getOwnerId()));
        quizById.values().forEach(quiz -> ownerIds.add(quiz.getOwnerId()));
        Map<UUID, User> userById = byId(users.findAllById(ownerIds), User::getId);
        Map<UUID, Long> questionCounts = questionCounts(quizById.keySet());
        Map<UUID, Long> topicQuizCounts = topicQuizCounts(topicById.keySet());

        Map<UUID, ClassroomCollaborationDtos.ResourcePreview> result = new HashMap<>();
        for (ClassroomMessage message : messages) {
            if (message.getDeletedAt() != null) continue;
            if (message.getTopicShareId() != null) {
                ClassroomTopicShare share = shareById.get(message.getTopicShareId());
                Topic topic = share == null ? null : topicById.get(share.getTopicId());
                result.put(message.getId(), topicPreview(
                        message.getClassroomId(), share, topic, userById,
                        topicQuizCounts.getOrDefault(topic == null ? null : topic.getId(), 0L)));
            } else if (message.getAssignmentId() != null) {
                Assignment assignment = assignmentById.get(message.getAssignmentId());
                Quiz quiz = assignment == null ? null : quizById.get(assignment.getQuizId());
                result.put(message.getId(), quizPreview(
                        message.getClassroomId(), assignment, quiz, userById,
                        questionCounts.getOrDefault(quiz == null ? null : quiz.getId(), 0L)));
            }
        }
        return result;
    }

    @Transactional(readOnly = true)
    public Map<UUID, ClassroomCollaborationDtos.ResourcePreview> topicPreviews(
            UUID classroomId, Collection<ClassroomTopicShare> values) {
        Map<UUID, Topic> topicById = byId(topics.findAllById(values.stream()
                .map(ClassroomTopicShare::getTopicId).collect(Collectors.toSet())), Topic::getId);
        Map<UUID, User> userById = byId(users.findAllById(topicById.values().stream()
                .map(Topic::getOwnerId).collect(Collectors.toSet())), User::getId);
        Map<UUID, Long> counts = topicQuizCounts(topicById.keySet());
        return values.stream().collect(Collectors.toMap(
                ClassroomTopicShare::getId,
                share -> {
                    Topic topic = topicById.get(share.getTopicId());
                    return topicPreview(classroomId, share, topic, userById,
                            counts.getOrDefault(share.getTopicId(), 0L));
                }));
    }

    @Transactional(readOnly = true)
    public ClassroomCollaborationDtos.TopicResourceDetail topicDetail(
            UUID actorId, UUID classroomId, UUID shareId) {
        requireMember(classroomId, actorId);
        ClassroomTopicShare share = shares.findByIdAndClassroomId(shareId, classroomId)
                .orElseThrow(() -> notFound("RESOURCE_NOT_FOUND",
                        "Không tìm thấy tài nguyên được chia sẻ."));
        if (share.getRevokedAt() != null) {
            throw new ApiException(HttpStatus.CONFLICT, "RESOURCE_SHARE_REVOKED",
                    "Chủ đề này không còn được chia sẻ trong lớp học.");
        }
        Topic topic = topics.findByIdAndDeletedAtIsNull(share.getTopicId())
                .filter(value -> value.getModerationStatus() == ModerationStatus.ACTIVE)
                .orElseThrow(() -> notFound("RESOURCE_NOT_FOUND",
                        "Chủ đề không còn khả dụng."));
        List<Quiz> visibleQuizzes = quizzes
                .findByTopicIdAndStatusAndVisibilityAndModerationStatusAndDeletedAtIsNullOrderByPublishedAtDesc(
                        topic.getId(), QuizStatus.PUBLISHED, Visibility.PUBLIC, ModerationStatus.ACTIVE);
        Map<UUID, Long> counts = questionCounts(
                visibleQuizzes.stream().map(Quiz::getId).toList());
        return new ClassroomCollaborationDtos.TopicResourceDetail(
                topicPreview(classroomId, share, topic, ownerMap(topic.getOwnerId()),
                        visibleQuizzes.size()),
                TopicDtos.Response.from(topic),
                visibleQuizzes.stream().map(quiz -> QuizDtos.QuizResponse.from(
                        quiz, counts.getOrDefault(quiz.getId(), 0L))).toList());
    }

    @Transactional(readOnly = true)
    public ClassroomCollaborationDtos.QuizResourceDetail quizDetail(
            UUID actorId, UUID classroomId, UUID assignmentId) {
        requireMember(classroomId, actorId);
        Assignment assignment = assignments.findByIdAndDeletedAtIsNull(assignmentId)
                .filter(value -> value.getClassroomId().equals(classroomId))
                .orElseThrow(() -> notFound("RESOURCE_NOT_FOUND",
                        "Không tìm thấy Quiz được chia sẻ."));
        if (assignment.getStatus() == AssignmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "ASSIGNMENT_NOT_AVAILABLE",
                    "Quiz này chưa được chia sẻ với lớp học.");
        }
        Quiz quiz = quizzes.findByIdAndDeletedAtIsNull(assignment.getQuizId())
                .filter(value -> value.getModerationStatus() == ModerationStatus.ACTIVE)
                .orElseThrow(() -> notFound("RESOURCE_NOT_FOUND",
                        "Quiz không còn khả dụng."));
        if (quiz.getStatus() != QuizStatus.PUBLISHED) {
            throw new ApiException(HttpStatus.CONFLICT, "QUIZ_NOT_PUBLISHED",
                    "Quiz này chưa được xuất bản.");
        }
        long questionCount = questions.countByQuizId(quiz.getId());
        return new ClassroomCollaborationDtos.QuizResourceDetail(
                quizPreview(classroomId, assignment, quiz,
                        ownerMap(quiz.getOwnerId()), questionCount),
                QuizDtos.QuizResponse.from(quiz, questionCount),
                ClassroomDtos.AssignmentResponse.from(assignment));
    }

    private ClassroomCollaborationDtos.ResourcePreview topicPreview(
            UUID classroomId, ClassroomTopicShare share, Topic topic,
            Map<UUID, User> userById, long quizCount) {
        boolean available = share != null && share.getClassroomId().equals(classroomId)
                && share.getRevokedAt() == null && topic != null
                && topic.getDeletedAt() == null
                && topic.getModerationStatus() == ModerationStatus.ACTIVE;
        return new ClassroomCollaborationDtos.ResourcePreview(
                "TOPIC", topic == null ? null : topic.getId(),
                share == null ? null : share.getId(),
                available ? topic.getTitle() : "Chủ đề không còn khả dụng",
                available ? previewText(topic.getDescription()) : null,
                available ? username(userById, topic.getOwnerId()) : null,
                available, available ? null : topicUnavailableReason(share, topic),
                available ? quizCount : 0,
                0, null, null, null, null, null, null);
    }

    private ClassroomCollaborationDtos.ResourcePreview quizPreview(
            UUID classroomId, Assignment assignment, Quiz quiz,
            Map<UUID, User> userById, long questionCount) {
        boolean available = assignment != null
                && assignment.getClassroomId().equals(classroomId)
                && assignment.getDeletedAt() == null && quiz != null
                && quiz.getDeletedAt() == null
                && quiz.getModerationStatus() == ModerationStatus.ACTIVE;
        return new ClassroomCollaborationDtos.ResourcePreview(
                "QUIZ", quiz == null ? null : quiz.getId(),
                assignment == null ? null : assignment.getId(),
                available ? quiz.getTitle() : "Quiz không còn khả dụng",
                available ? previewText(quiz.getDescription()) : null,
                available ? username(userById, quiz.getOwnerId()) : null,
                available, available ? null : "RESOURCE_UNAVAILABLE",
                0, available ? questionCount : 0,
                available ? quiz.getDifficulty() : null,
                available ? assignment.getDurationMinutes() : null,
                available ? assignment.getStatus() : null,
                available ? assignment.getOpensAt() : null,
                available ? assignment.getDueAt() : null,
                available ? assignment.getMaxAttempts() : null);
    }

    private Map<UUID, Long> questionCounts(Collection<UUID> quizIds) {
        if (quizIds.isEmpty()) return Map.of();
        return questions.countByQuizIds(quizIds).stream().collect(Collectors.toMap(
                QuestionRepository.QuizQuestionCount::getQuizId,
                QuestionRepository.QuizQuestionCount::getQuestionCount));
    }

    private Map<UUID, Long> topicQuizCounts(Collection<UUID> topicIds) {
        if (topicIds.isEmpty()) return Map.of();
        return quizzes.countPublicPublishedByTopicIds(topicIds).stream()
                .collect(Collectors.toMap(
                        QuizRepository.TopicQuizCount::getTopicId,
                        QuizRepository.TopicQuizCount::getQuizCount));
    }

    private Map<UUID, User> ownerMap(UUID ownerId) {
        return byId(users.findAllById(List.of(ownerId)), User::getId);
    }

    private void requireMember(UUID classroomId, UUID actorId) {
        members.findByClassroomIdAndUserId(classroomId, actorId)
                .filter(ClassroomMember::isActive)
                .orElseThrow(() -> new ApiException(HttpStatus.FORBIDDEN,
                        "CLASSROOM_ACCESS_DENIED",
                        "Bạn không có quyền truy cập lớp học này."));
    }

    private static String username(Map<UUID, User> users, UUID ownerId) {
        User user = users.get(ownerId);
        return user == null ? "Người dùng" : user.getUsername();
    }

    private static String previewText(String value) {
        if (value == null || value.isBlank()) return null;
        String normalized = value.strip().replaceAll("\\s+", " ");
        return normalized.length() <= 240
                ? normalized : normalized.substring(0, 237) + "...";
    }

    private static String topicUnavailableReason(
            ClassroomTopicShare share, Topic topic) {
        if (share != null && share.getRevokedAt() != null) {
            return "RESOURCE_SHARE_REVOKED";
        }
        if (topic != null
                && topic.getModerationStatus() != ModerationStatus.ACTIVE) {
            return "RESOURCE_HIDDEN";
        }
        return "RESOURCE_UNAVAILABLE";
    }

    private static ApiException notFound(String code, String message) {
        return new ApiException(HttpStatus.NOT_FOUND, code, message);
    }

    private static <T> Map<UUID, T> byId(
            Collection<T> values, Function<T, UUID> id) {
        return values.stream().collect(Collectors.toMap(id, Function.identity()));
    }
}
