package com.genquiz.bk.abuse;

public record AbuseRequestIdentity(String ipHash, String deviceHash, String challengeToken) {}
