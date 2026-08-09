package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class CognitivePolicyTest {
    @Test
    void acceptsCanonicalProfilesForEveryLevel() {
        assertDoesNotThrow(() -> CognitivePolicy.validate(CognitiveLevel.L1,
                profile(1, 0, false, true, false)));
        assertDoesNotThrow(() -> CognitivePolicy.validate(CognitiveLevel.L2,
                profile(2, 1, false, false, false)));
        assertDoesNotThrow(() -> CognitivePolicy.validate(CognitiveLevel.L3,
                profile(2, 1, true, false, false)));
        assertDoesNotThrow(() -> CognitivePolicy.validate(CognitiveLevel.L4,
                profile(2, 2, true, false, true)));
        assertDoesNotThrow(() -> CognitivePolicy.validate(CognitiveLevel.L5,
                profile(3, 3, true, false, true)));
    }

    @Test
    void rejectsAProfileWhoseScoreDoesNotBelongToTheLevel() {
        assertThrows(ResponseStatusException.class, () -> CognitivePolicy.validate(
                CognitiveLevel.L4, profile(4, 3, true, false, true)));
    }

    private static CognitiveProfile profile(int concepts, int reasoning, boolean scenario,
                                            boolean direct, boolean comparison) {
        return new CognitiveProfile(concepts, reasoning, scenario, direct, comparison,
                java.util.stream.IntStream.range(0, concepts)
                        .mapToObj(index -> "concept-" + index).toList(),
                scenario ? "Tình huống mới" : null, true);
    }
}
