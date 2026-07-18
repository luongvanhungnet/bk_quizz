package com.genquiz.bk.classroom;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.notification.NotificationService;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ClassroomServiceTest {
    @Mock ClassroomRepository classrooms;
    @Mock ClassroomMemberRepository members;
    @Mock UserRepository users;
    @Mock NotificationService notifications;

    @Test
    void verifiedTeacherCreatesClassroomAndOwnerMembership() {
        UUID teacherId = UUID.randomUUID();
        User teacher = user(Role.TEACHER, true);
        when(users.findById(teacherId)).thenReturn(Optional.of(teacher));
        when(classrooms.existsByJoinCodeIgnoreCaseAndDeletedAtIsNull(any())).thenReturn(false);
        when(classrooms.save(any())).thenAnswer(invocation -> invocation.getArgument(0));
        when(members.save(any())).thenAnswer(invocation -> invocation.getArgument(0));

        ClassroomService service = service();
        ClassroomDtos.ClassroomResponse result = service.create(teacherId,
                new ClassroomDtos.SaveRequest("Cấu trúc dữ liệu", "Lớp ôn tập"));

        assertEquals(teacherId, result.ownerId());
        assertEquals(ClassroomStatus.ACTIVE, result.status());
        assertTrue(result.joinCode().matches("[A-Z2-9]{8}"));
        ArgumentCaptor<ClassroomMember> membership = ArgumentCaptor.forClass(ClassroomMember.class);
        verify(members).save(membership.capture());
        assertEquals(ClassroomMemberRole.TEACHER, membership.getValue().getRole());
        assertEquals(teacherId, membership.getValue().getUserId());
    }

    @Test
    void studentCannotCreateClassroom() {
        UUID studentId = UUID.randomUUID();
        when(users.findById(studentId)).thenReturn(Optional.of(user(Role.STUDENT, true)));

        ApiException error = assertThrows(ApiException.class, () -> service().create(studentId,
                new ClassroomDtos.SaveRequest("Lớp", null)));

        assertEquals("TEACHER_REQUIRED", error.code());
        verify(classrooms, never()).save(any());
    }

    @Test
    void joiningTwiceIsRejected() {
        UUID userId = UUID.randomUUID();
        UUID ownerId = UUID.randomUUID();
        Instant now = Instant.now();
        Classroom classroom = new Classroom(ownerId, "Lớp", null, "ABC23456", now);
        ClassroomMember active = new ClassroomMember(classroom.getId(), userId, ClassroomMemberRole.STUDENT, now);
        when(users.findById(userId)).thenReturn(Optional.of(user(Role.STUDENT, true)));
        when(classrooms.findByJoinCodeIgnoreCaseAndDeletedAtIsNull("ABC23456")).thenReturn(Optional.of(classroom));
        when(members.findByClassroomIdAndUserId(classroom.getId(), userId)).thenReturn(Optional.of(active));

        ApiException error = assertThrows(ApiException.class,
                () -> service().join(userId, "abc23456"));

        assertEquals("ALREADY_CLASSROOM_MEMBER", error.code());
    }

    private ClassroomService service() {
        return new ClassroomService(classrooms, members, users, notifications);
    }

    private static User user(Role role, boolean verified) {
        User user = new User("tester", UUID.randomUUID() + "@example.com", "x".repeat(60));
        user.setRole(role);
        if (verified) user.verifyEmail();
        return user;
    }
}
