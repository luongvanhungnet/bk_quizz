package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class QuestionServiceValidationTest {

    @Test
    void acceptsAWellFormedSingleChoiceQuestion() {
        var request = request(QuestionType.SINGLE_CHOICE,
                List.of(option("A", true), option("B", false), option("C", false), option("D", false)), List.of());
        assertDoesNotThrow(() -> QuestionService.validate(request));
    }

    @Test
    void rejectsMultipleSelectWithOnlyOneCorrectOption() {
        var request = request(QuestionType.MULTIPLE_SELECT,
                List.of(option("A", true), option("B", false), option("C", false), option("D", false)), List.of());
        assertThrows(ResponseStatusException.class, () -> QuestionService.validate(request));
    }

    @Test
    void rejectsDuplicateFillBlankAnswersAfterNormalization() {
        var request = request(QuestionType.FILL_BLANK, List.of(), List.of("Hà Nội", "  hà   nội "));
        assertThrows(ResponseStatusException.class, () -> QuestionService.validate(request));
    }

    @Test
    void rejectsGeneratedBatchWithDuplicatePrompts() {
        var first = request(QuestionType.SINGLE_CHOICE,
                List.of(option("A", true), option("B", false), option("C", false), option("D", false)), List.of());
        var duplicate = new QuizDtos.QuestionRequest(first.type(), "  CÂU   HỎI? ", first.explanation(), first.points(),
                first.difficulty(), null, first.options(), first.acceptedAnswers());
        assertThrows(ResponseStatusException.class, () -> QuestionService.validateGeneratedBatch(
                List.of(first, duplicate), new QuizDtos.QuestionCounts(2, 0, 0)));
    }

    @Test
    void acceptsGeneratedBatchWithExactCounts() {
        var single = request(QuestionType.SINGLE_CHOICE,
                List.of(option("A", true), option("B", false), option("C", false), option("D", false)), List.of());
        var fill = new QuizDtos.QuestionRequest(QuestionType.FILL_BLANK, "Điền đáp án", "Giải thích",
                BigDecimal.ONE, Difficulty.MEDIUM, null, List.of(), List.of("Đáp án"));

        assertDoesNotThrow(() -> QuestionService.validateGeneratedBatch(
                List.of(single, fill), new QuizDtos.QuestionCounts(1, 0, 1)));
    }

    @Test
    void rejectsMixedDifficultyBeforeWritingAQuestion() {
        var mixed = new QuizDtos.QuestionRequest(QuestionType.SINGLE_CHOICE, "Câu hỏi?", "Giải thích",
                BigDecimal.ONE, Difficulty.MIXED, null,
                List.of(option("A", true), option("B", false), option("C", false), option("D", false)),
                List.of());

        assertThrows(ResponseStatusException.class, () -> QuestionService.validate(mixed));
    }

    @Test
    void rejectsGeneratedBatchWithWrongCounts() {
        var single = request(QuestionType.SINGLE_CHOICE,
                List.of(option("A", true), option("B", false), option("C", false), option("D", false)), List.of());

        assertThrows(ResponseStatusException.class, () -> QuestionService.validateGeneratedBatch(
                List.of(single), new QuizDtos.QuestionCounts(0, 1, 0)));
    }

    @Test
    void rejectsAQuestionWithZeroPointsBeforeWritingToTheDatabase() {
        var request = new QuizDtos.QuestionRequest(
                QuestionType.SINGLE_CHOICE,
                "Câu hỏi?",
                "Giải thích",
                BigDecimal.ZERO,
                Difficulty.MEDIUM,
                null,
                List.of(option("A", true), option("B", false), option("C", false), option("D", false)),
                List.of());

        assertThrows(ResponseStatusException.class, () -> QuestionService.validate(request));
    }

    private static QuizDtos.QuestionRequest request(QuestionType type, List<QuizDtos.OptionRequest> options,
                                                     List<String> acceptedAnswers) {
        return new QuizDtos.QuestionRequest(type, "Câu hỏi?", "Giải thích", BigDecimal.ONE,
                Difficulty.MEDIUM, null, options, acceptedAnswers);
    }

    private static QuizDtos.OptionRequest option(String text, boolean correct) {
        return new QuizDtos.OptionRequest(text, correct);
    }
}
