package com.genquiz.bk.classroom;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.UUID;
import com.genquiz.bk.common.error.ApiException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RealtimeTokenServiceTest {
    @Mock ClassroomMemberRepository members;
    @Mock AblyTokenSigner signer;

    @Test
    void createsSubscribeOnlyTokenForAnActiveClassroomMember() {
        UUID userId = UUID.randomUUID();
        UUID classroomId = UUID.randomUUID();
        AblyTokenRequest expected = new AblyTokenRequest(
                "key-name", 900_000L, "capability", userId.toString(), 123L, "nonce", "mac");
        when(members.existsByClassroomIdAndUserIdAndStatus(
                classroomId, userId, ClassroomMemberStatus.ACTIVE)).thenReturn(true);
        when(signer.createSubscribeToken(userId, classroomId)).thenReturn(expected);

        RealtimeTokenService service = new RealtimeTokenService(members, signer);

        assertThat(service.createToken(userId, classroomId)).isSameAs(expected);
        verify(signer).createSubscribeToken(userId, classroomId);
    }

    @Test
    void hidesAClassroomFromUsersWhoAreNotActiveMembers() {
        UUID userId = UUID.randomUUID();
        UUID classroomId = UUID.randomUUID();

        RealtimeTokenService service = new RealtimeTokenService(members, signer);

        assertThatThrownBy(() -> service.createToken(userId, classroomId))
                .isInstanceOf(ApiException.class)
                .extracting("code")
                .isEqualTo("CLASSROOM_NOT_FOUND");
    }
}
