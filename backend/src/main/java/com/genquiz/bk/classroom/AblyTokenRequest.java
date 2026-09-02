package com.genquiz.bk.classroom;

record AblyTokenRequest(
        String keyName,
        long ttl,
        String capability,
        String clientId,
        long timestamp,
        String nonce,
        String mac
) {}
