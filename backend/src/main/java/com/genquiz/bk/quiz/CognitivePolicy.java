package com.genquiz.bk.quiz;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

public final class CognitivePolicy {
    private CognitivePolicy() {}

    public static void validate(CognitiveLevel level, CognitiveProfile profile) {
        int k = profile.conceptCount();
        int r = profile.reasoningStepCount();
        int score = profile.complexityScore();
        boolean valid = profile.conceptsUsed().size() == k && switch (level) {
            case L1 -> k == 1 && r == 0 && !profile.requiresNovelScenario()
                    && profile.answerDirectlyPresent() && !profile.requiresComparison()
                    && score >= 1 && score <= 2;
            case L2 -> k >= 1 && k <= 2 && r == 1 && !profile.requiresNovelScenario()
                    && !profile.answerDirectlyPresent() && !profile.requiresComparison()
                    && score >= 3 && score <= 4;
            case L3 -> k >= 1 && k <= 2 && r >= 1 && r <= 2 && profile.requiresNovelScenario()
                    && !profile.answerDirectlyPresent() && !profile.requiresComparison()
                    && score >= 5 && score <= 7;
            case L4 -> k >= 2 && k <= 4 && r >= 2 && r <= 3 && profile.requiresNovelScenario()
                    && !profile.answerDirectlyPresent() && profile.requiresComparison()
                    && score >= 8 && score <= 10;
            case L5 -> k >= 3 && k <= 6 && r >= 3 && r <= 5 && profile.requiresNovelScenario()
                    && !profile.answerDirectlyPresent() && profile.requiresComparison() && score >= 11;
        };
        if (!valid) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "COGNITIVE_CONSTRAINT_VIOLATION");
        }
    }
}
