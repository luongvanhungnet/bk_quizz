package com.genquiz.bk.classroom;

import com.genquiz.bk.common.ModerationStatus;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.attempt.AnswerReleasePolicy;
import com.genquiz.bk.quiz.QuestionRepository;
import com.genquiz.bk.quiz.Quiz;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.quiz.QuizStatus;
import com.genquiz.bk.topic.Topic;
import com.genquiz.bk.topic.TopicRepository;
import com.genquiz.bk.topic.Visibility;
import com.genquiz.bk.user.UserRepository;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ClassroomResourcePresentationServiceTest {
    @Mock ClassroomMemberRepository members;
    @Mock ClassroomTopicShareRepository shares;
    @Mock AssignmentRepository assignments;
    @Mock TopicRepository topics;
    @Mock QuizRepository quizzes;
    @Mock QuestionRepository questions;
    @Mock UserRepository users;

    @Test
    void topicDetailOnlyReturnsPublicPublishedQuizzes() {
        UUID classroomId = UUID.randomUUID();
        UUID actorId = UUID.randomUUID();
        UUID ownerId = UUID.randomUUID();
        ClassroomMember member = new ClassroomMember(
                classroomId, actorId, ClassroomMemberRole.STUDENT, Instant.now());
        Topic topic = new Topic(ownerId, "Cấu trúc dữ liệu", "Mô tả", Visibility.PRIVATE);
        ClassroomTopicShare share = new ClassroomTopicShare(
                classroomId, topic.getId(), ownerId, Instant.now());
        Quiz visible = Quiz.manual(topic.getId(), ownerId, "Quiz công khai",
                null, com.genquiz.bk.quiz.Difficulty.MEDIUM, 20, Visibility.PUBLIC);
        visible.publish(Instant.now());

        when(members.findByClassroomIdAndUserId(classroomId, actorId))
                .thenReturn(Optional.of(member));
        when(shares.findByIdAndClassroomId(share.getId(), classroomId))
                .thenReturn(Optional.of(share));
        when(topics.findByIdAndDeletedAtIsNull(topic.getId()))
                .thenReturn(Optional.of(topic));
        when(quizzes.findByTopicIdAndStatusAndVisibilityAndModerationStatusAndDeletedAtIsNullOrderByPublishedAtDesc(
                topic.getId(), QuizStatus.PUBLISHED, Visibility.PUBLIC, ModerationStatus.ACTIVE))
                .thenReturn(List.of(visible));
        when(questions.countByQuizIds(List.of(visible.getId()))).thenReturn(List.of());

        var detail = service().topicDetail(actorId, classroomId, share.getId());

        assertEquals(topic.getId(), detail.topic().id());
        assertEquals(List.of(visible.getId()),
                detail.quizzes().stream().map(value -> value.id()).toList());
    }

    @Test
    void topicDetailRejectsRevokedShare() {
        UUID classroomId = UUID.randomUUID();
        UUID actorId = UUID.randomUUID();
        ClassroomMember member = new ClassroomMember(
                classroomId, actorId, ClassroomMemberRole.STUDENT, Instant.now());
        ClassroomTopicShare share = new ClassroomTopicShare(
                classroomId, UUID.randomUUID(), actorId, Instant.now());
        share.revoke(Instant.now());
        when(members.findByClassroomIdAndUserId(classroomId, actorId))
                .thenReturn(Optional.of(member));
        when(shares.findByIdAndClassroomId(share.getId(), classroomId))
                .thenReturn(Optional.of(share));

        ApiException error = assertThrows(ApiException.class,
                () -> service().topicDetail(actorId, classroomId, share.getId()));

        assertEquals("RESOURCE_SHARE_REVOKED", error.code());
    }

    @Test
    void quizDetailDoesNotRevealAssignmentFromAnotherClassroom() {
        UUID classroomId = UUID.randomUUID();
        UUID otherClassroomId = UUID.randomUUID();
        UUID actorId = UUID.randomUUID();
        ClassroomMember member = new ClassroomMember(
                classroomId, actorId, ClassroomMemberRole.STUDENT, Instant.now());
        Assignment assignment = new Assignment(otherClassroomId, UUID.randomUUID(),
                actorId, "Quiz riêng", null, null, null, 20, 1,
                AnswerReleasePolicy.IMMEDIATE, Instant.now());
        assignment.publish(Instant.now());
        when(members.findByClassroomIdAndUserId(classroomId, actorId))
                .thenReturn(Optional.of(member));
        when(assignments.findByIdAndDeletedAtIsNull(assignment.getId()))
                .thenReturn(Optional.of(assignment));

        ApiException error = assertThrows(ApiException.class,
                () -> service().quizDetail(actorId, classroomId, assignment.getId()));

        assertEquals("RESOURCE_NOT_FOUND", error.code());
    }

    private ClassroomResourcePresentationService service() {
        return new ClassroomResourcePresentationService(
                members, shares, assignments, topics, quizzes, questions, users);
    }
}
