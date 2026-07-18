package com.genquiz.bk.classroom;

import com.genquiz.bk.attempt.AnswerReleasePolicy;
import com.genquiz.bk.attempt.AssignmentPolicyGateway;
import com.genquiz.bk.attempt.AttemptRepository;
import com.genquiz.bk.attempt.AttemptStatus;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.notification.NotificationService;
import com.genquiz.bk.quiz.QuizRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AssignmentServiceTest {
    @Mock AssignmentRepository assignments;
    @Mock AssignmentSubmissionRepository submissions;
    @Mock ClassroomRepository classrooms;
    @Mock ClassroomMemberRepository members;
    @Mock QuizRepository quizzes;
    @Mock AttemptRepository attempts;
    @Mock NotificationService notifications;

    @Test
    void policyAuthorizesActiveMemberWithinWindowAndBelowLimit() {
        UUID ownerId = UUID.randomUUID();
        UUID studentId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        Instant now = Instant.parse("2026-07-11T05:00:00Z");
        Classroom classroom = new Classroom(ownerId, "Backend", null, "ABC23456", now.minusSeconds(3600));
        ClassroomMember member = new ClassroomMember(classroom.getId(), studentId,
                ClassroomMemberRole.STUDENT, now.minusSeconds(3600));
        Assignment assignment = new Assignment(classroom.getId(), quizId, ownerId, "Bài 1", null,
                now.minusSeconds(60), now.plusSeconds(3600), 30, 2,
                AnswerReleasePolicy.AFTER_DUE_DATE, now.minusSeconds(120));
        assignment.publish(now.minusSeconds(90));
        when(assignments.findByIdAndDeletedAtIsNull(assignment.getId())).thenReturn(Optional.of(assignment));
        when(classrooms.findByIdAndDeletedAtIsNull(classroom.getId())).thenReturn(Optional.of(classroom));
        when(members.findByClassroomIdAndUserId(classroom.getId(), studentId)).thenReturn(Optional.of(member));
        when(attempts.existsByAssignmentIdAndUserIdAndStatus(assignment.getId(), studentId,
                AttemptStatus.IN_PROGRESS)).thenReturn(false);
        when(attempts.maxAssignmentAttemptNumber(assignment.getId(), studentId)).thenReturn(1);

        AssignmentPolicyGateway.Policy policy = service().authorizeStart(assignment.getId(), quizId, studentId, now);

        assertEquals(30, policy.durationMinutes());
        assertEquals(2, policy.maxAttempts());
        assertEquals(AnswerReleasePolicy.AFTER_DUE_DATE, policy.answerReleasePolicy());
    }

    @Test
    void policyRejectsWhenMaximumAttemptsReached() {
        UUID ownerId = UUID.randomUUID();
        UUID studentId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        Instant now = Instant.now();
        Classroom classroom = new Classroom(ownerId, "Backend", null, "ABC23456", now.minusSeconds(3600));
        ClassroomMember member = new ClassroomMember(classroom.getId(), studentId,
                ClassroomMemberRole.STUDENT, now.minusSeconds(3600));
        Assignment assignment = new Assignment(classroom.getId(), quizId, ownerId, "Bài 1", null,
                null, now.plusSeconds(3600), 30, 1, AnswerReleasePolicy.IMMEDIATE, now.minusSeconds(120));
        assignment.publish(now.minusSeconds(90));
        when(assignments.findByIdAndDeletedAtIsNull(assignment.getId())).thenReturn(Optional.of(assignment));
        when(classrooms.findByIdAndDeletedAtIsNull(classroom.getId())).thenReturn(Optional.of(classroom));
        when(members.findByClassroomIdAndUserId(classroom.getId(), studentId)).thenReturn(Optional.of(member));
        when(attempts.maxAssignmentAttemptNumber(assignment.getId(), studentId)).thenReturn(1);

        ApiException error = assertThrows(ApiException.class,
                () -> service().authorizeStart(assignment.getId(), quizId, studentId, now));

        assertEquals("MAX_ATTEMPTS_REACHED", error.code());
    }

    private AssignmentService service() {
        return new AssignmentService(assignments, submissions, classrooms, members, quizzes, attempts, notifications);
    }
}
