package com.genquiz.bk.quiz;

import java.util.List;

public record CognitiveProfile(
        int conceptCount,
        int reasoningStepCount,
        boolean requiresNovelScenario,
        boolean answerDirectlyPresent,
        boolean requiresComparison,
        List<String> conceptsUsed,
        String novelScenarioSummary,
        boolean verified) {
    public CognitiveProfile {
        conceptsUsed = conceptsUsed == null ? List.of() : List.copyOf(conceptsUsed);
    }

    public int complexityScore() {
        return conceptCount + 2 * reasoningStepCount
                + (requiresNovelScenario ? 1 : 0)
                + (requiresComparison ? 1 : 0);
    }
}
