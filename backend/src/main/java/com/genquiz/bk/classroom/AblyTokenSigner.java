package com.genquiz.bk.classroom;

import java.util.UUID;

interface AblyTokenSigner {
    AblyTokenRequest createSubscribeToken(UUID userId, UUID classroomId);
}
