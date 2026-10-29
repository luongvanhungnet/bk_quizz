package com.genquiz.bk.rag;

@FunctionalInterface
public interface RagIdentityTokenProvider {
    String token(String audience);
}
