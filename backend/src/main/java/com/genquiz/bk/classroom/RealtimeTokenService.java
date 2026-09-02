package com.genquiz.bk.classroom;

import com.genquiz.bk.common.error.ApiException;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(name = "bkquiz.realtime.provider", havingValue = "ably")
class RealtimeTokenService {
    private final ClassroomMemberRepository members;
    private final AblyTokenSigner signer;

    RealtimeTokenService(ClassroomMemberRepository members, AblyTokenSigner signer) {
        this.members = members;
        this.signer = signer;
    }

    AblyTokenRequest createToken(UUID userId, UUID classroomId) {
        if (!members.existsByClassroomIdAndUserIdAndStatus(
                classroomId, userId, ClassroomMemberStatus.ACTIVE)) {
            throw new ApiException(HttpStatus.NOT_FOUND, "CLASSROOM_NOT_FOUND", "Không tìm thấy lớp học.");
        }
        return signer.createSubscribeToken(userId, classroomId);
    }
}
