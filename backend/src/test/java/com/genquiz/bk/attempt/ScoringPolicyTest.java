package com.genquiz.bk.attempt;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.genquiz.bk.quiz.QuestionType;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ScoringPolicyTest {
    private final UUID first = UUID.randomUUID();
    private final UUID second = UUID.randomUUID();

    @Test
    void singleChoiceRequiresExactlyTheCorrectOption() {
        assertTrue(ScoringPolicy.isCorrect(QuestionType.SINGLE_CHOICE, List.of(first), null,
                List.of(first), List.of()));
        assertFalse(ScoringPolicy.isCorrect(QuestionType.SINGLE_CHOICE, List.of(first, second), null,
                List.of(first), List.of()));
    }

    @Test
    void multipleSelectDoesNotAwardPartialCredit() {
        assertTrue(ScoringPolicy.isCorrect(QuestionType.MULTIPLE_SELECT, List.of(second, first), null,
                List.of(first, second), List.of()));
        assertFalse(ScoringPolicy.isCorrect(QuestionType.MULTIPLE_SELECT, List.of(first), null,
                List.of(first, second), List.of()));
        assertFalse(ScoringPolicy.isCorrect(QuestionType.MULTIPLE_SELECT, List.of(first, first, second), null,
                List.of(first, second), List.of()));
    }

    @Test
    void fillBlankIgnoresCaseAndWhitespaceButKeepsVietnameseDiacritics() {
        assertTrue(ScoringPolicy.isCorrect(QuestionType.FILL_BLANK, List.of(), "  HÀ   NỘI ",
                List.of(), List.of("Hà Nội")));
        assertFalse(ScoringPolicy.isCorrect(QuestionType.FILL_BLANK, List.of(), "Ha Noi",
                List.of(), List.of("Hà Nội")));
    }
}
