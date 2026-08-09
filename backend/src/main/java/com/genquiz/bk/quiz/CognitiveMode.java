package com.genquiz.bk.quiz;

public enum CognitiveMode {
    L1, L2, L3, L4, L5, BALANCED;

    public CognitiveLevel fixedLevel() {
        if (this == BALANCED) {
            throw new IllegalStateException("BALANCED không phải level của một câu hỏi.");
        }
        return CognitiveLevel.valueOf(name());
    }
}
