package com.genquiz.bk.abuse;

public interface ChallengeVerifier {
    boolean verify(String token, String ipHash);
}
