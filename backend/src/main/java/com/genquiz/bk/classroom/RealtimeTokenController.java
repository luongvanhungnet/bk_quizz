package com.genquiz.bk.classroom;

import com.genquiz.bk.common.api.ApiEnvelope;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/realtime")
@ConditionalOnProperty(name = "bkquiz.realtime.provider", havingValue = "ably")
class RealtimeTokenController {
    private final RealtimeTokenService service;

    RealtimeTokenController(RealtimeTokenService service) {
        this.service = service;
    }

    @PostMapping("/token")
    ApiEnvelope<AblyTokenRequest> token(@RequestParam UUID classroomId, Authentication authentication) {
        return ApiEnvelope.success("Đã cấp quyền kết nối realtime.",
                service.createToken(ClassroomController.actor(authentication), classroomId));
    }
}
