package com.genquiz.bk.attempt;

import com.genquiz.bk.quiz.AcceptedAnswer;
import com.genquiz.bk.quiz.QuestionType;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

public final class ScoringPolicy {
    private ScoringPolicy() {}

    public static boolean isCorrect(QuestionType type, Collection<UUID> selectedOptionIds, String textAnswer,
                                    Collection<UUID> correctOptionIds, Collection<String> acceptedAnswers) {
        Set<UUID> selected = selectedOptionIds == null ? Set.of() : new HashSet<>(selectedOptionIds);
        Set<UUID> correct = correctOptionIds == null ? Set.of() : new HashSet<>(correctOptionIds);
        if (selectedOptionIds != null && selected.size() != selectedOptionIds.size()) return false;
        return switch (type) {
            case SINGLE_CHOICE -> selected.size() == 1 && selected.equals(correct);
            case MULTIPLE_SELECT -> selected.equals(correct);
            case FILL_BLANK -> {
                String normalized = AcceptedAnswer.normalize(textAnswer);
                yield !normalized.isEmpty() && acceptedAnswers.stream()
                        .map(AcceptedAnswer::normalize).anyMatch(normalized::equals);
            }
        };
    }
}
