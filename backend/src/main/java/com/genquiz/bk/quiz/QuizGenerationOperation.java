package com.genquiz.bk.quiz;

public enum QuizGenerationOperation {
    CREATE,
    APPEND;

    public static QuizGenerationOperation fromPayload(String payload) {
        if (payload != null && payload.contains("\"operation\":\"APPEND\"")) {
            return APPEND;
        }
        return CREATE;
    }
}
