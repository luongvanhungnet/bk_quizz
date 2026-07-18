package com.genquiz.bk.security;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class VerifiedAccountGuardTest {
    @Test
    void rejectsUnverifiedAccountAtServiceBoundary() {
        UserRepository users = mock(UserRepository.class);
        User user = new User("Student", "student@example.com", "hash");
        when(users.findByIdAndDeletedAtIsNull(user.getId())).thenReturn(Optional.of(user));

        assertThatThrownBy(() -> new VerifiedAccountGuard(users).require(user.getId()))
                .isInstanceOf(ApiException.class)
                .extracting(error -> ((ApiException) error).code())
                .isEqualTo("EMAIL_NOT_VERIFIED");
    }
}
