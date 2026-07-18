package com.genquiz.bk.attempt;

import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.genquiz.bk.quiz.AcceptedAnswerRepository;
import com.genquiz.bk.quiz.Question;
import com.genquiz.bk.quiz.QuestionOption;
import com.genquiz.bk.quiz.QuestionOptionRepository;
import com.genquiz.bk.quiz.QuestionRepository;
import com.genquiz.bk.quiz.QuestionType;
import com.genquiz.bk.quiz.Quiz;
import com.genquiz.bk.quiz.QuizService;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.Collections;
import java.util.Random;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AttemptService {
    private final AttemptRepository attempts;
    private final AttemptQuestionSnapshotRepository snapshots;
    private final AttemptAnswerRepository answers;
    private final QuestionRepository questions;
    private final QuestionOptionRepository options;
    private final AcceptedAnswerRepository acceptedAnswers;
    private final QuizService quizzes;
    private final AssignmentPolicyGateway assignmentPolicies;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Autowired
    public AttemptService(AttemptRepository attempts, AttemptQuestionSnapshotRepository snapshots,
                          AttemptAnswerRepository answers, QuestionRepository questions,
                          QuestionOptionRepository options, AcceptedAnswerRepository acceptedAnswers,
                          QuizService quizzes, ObjectProvider<AssignmentPolicyGateway> assignmentPolicies,
                          ObjectMapper objectMapper) {
        this(attempts, snapshots, answers, questions, options, acceptedAnswers, quizzes,
                assignmentPolicies.getIfAvailable(), objectMapper, Clock.systemUTC());
    }

    AttemptService(AttemptRepository attempts, AttemptQuestionSnapshotRepository snapshots,
                   AttemptAnswerRepository answers, QuestionRepository questions,
                   QuestionOptionRepository options, AcceptedAnswerRepository acceptedAnswers,
                   QuizService quizzes, AssignmentPolicyGateway assignmentPolicies,
                   ObjectMapper objectMapper, Clock clock) {
        this.attempts = attempts;
        this.snapshots = snapshots;
        this.answers = answers;
        this.questions = questions;
        this.options = options;
        this.acceptedAnswers = acceptedAnswers;
        this.quizzes = quizzes;
        this.assignmentPolicies = assignmentPolicies;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public AttemptDtos.AttemptResponse start(UUID actorId, UUID quizId, UUID assignmentId) {
        Instant now = Instant.now(clock);
        AssignmentPolicyGateway.Policy policy = assignmentId == null ? null
                : authorizeAssignment(assignmentId, quizId, actorId, now);
        Quiz quiz = quizzes.getForAttempt(actorId, quizId, policy != null);
        List<Question> sourceQuestions = questions.findByQuizIdOrderByPosition(quizId);
        if (sourceQuestions.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Bài kiểm tra chưa có câu hỏi");
        }

        int attemptNumber;
        int durationMinutes;
        Instant dueAt = null;
        AnswerReleasePolicy releasePolicy = AnswerReleasePolicy.IMMEDIATE;
        if (policy == null) {
            attemptNumber = attempts.maxPracticeAttemptNumber(quizId, actorId) + 1;
            durationMinutes = quiz.getDurationMinutes();
        } else {
            if (attempts.existsByAssignmentIdAndUserIdAndStatus(assignmentId, actorId, AttemptStatus.IN_PROGRESS)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "Bạn đã có một lượt làm đang diễn ra cho bài tập này");
            }
            long completed = attempts.countByAssignmentIdAndUserIdAndStatus(
                    assignmentId, actorId, AttemptStatus.SUBMITTED);
            if (completed >= policy.maxAttempts()) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "Bạn đã sử dụng hết số lượt làm bài");
            }
            attemptNumber = attempts.maxAssignmentAttemptNumber(assignmentId, actorId) + 1;
            durationMinutes = policy.durationMinutes() > 0 ? policy.durationMinutes() : quiz.getDurationMinutes();
            dueAt = policy.dueAt();
            releasePolicy = policy.answerReleasePolicy();
        }

        Instant deadline = now.plus(durationMinutes, ChronoUnit.MINUTES);
        if (dueAt != null && dueAt.isBefore(deadline)) deadline = dueAt;
        if (!deadline.isAfter(now)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Đã hết thời gian làm bài");
        }

        boolean showScore = policy == null || policy.showScore();
        boolean allowReview = policy == null || policy.allowReview();
        Attempt attempt = attempts.save(new Attempt(quizId, assignmentId, actorId, attemptNumber,
                sourceQuestions.size(), now, deadline, releasePolicy, dueAt, showScore, allowReview));
        List<Question> orderedQuestions = new ArrayList<>(sourceQuestions);
        Random random = new Random(attempt.getId().getMostSignificantBits() ^ attempt.getId().getLeastSignificantBits());
        if (policy != null && policy.shuffleQuestions()) Collections.shuffle(orderedQuestions, random);
        List<AttemptQuestionSnapshot> values = new ArrayList<>();
        for (int index = 0; index < orderedQuestions.size(); index++) {
            values.add(snapshot(attempt.getId(), orderedQuestions.get(index), index + 1,
                    policy != null && policy.shuffleOptions(), random));
        }
        snapshots.saveAll(values);
        attempts.flush();
        return takingResponse(attempt, values, List.of());
    }

    @Transactional(readOnly = true)
    public AttemptDtos.AttemptResponse get(UUID actorId, UUID attemptId) {
        Attempt attempt = requireOwned(actorId, attemptId);
        if (attempt.getStatus() != AttemptStatus.IN_PROGRESS) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Lượt làm bài đã kết thúc; hãy dùng endpoint kết quả");
        }
        return takingResponse(attempt, snapshots.findByAttemptIdOrderByPosition(attemptId),
                answers.findByAttemptId(attemptId));
    }

    @Transactional
    public AttemptDtos.AttemptResponse autosave(UUID actorId, UUID attemptId,
                                                AttemptDtos.AutosaveRequest request) {
        Attempt attempt = requireOwned(actorId, attemptId);
        if (attempt.getStatus() != AttemptStatus.IN_PROGRESS) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Lượt làm bài đã kết thúc");
        }
        if (attempt.getVersion() != request.attemptVersion()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Dữ liệu làm bài đã thay đổi ở thiết bị khác; vui lòng tải lại");
        }
        Instant now = Instant.now(clock);
        if (now.isAfter(attempt.getExpiresAt())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Đã hết thời gian làm bài; vui lòng nộp bài");
        }
        Set<UUID> requestIds = new HashSet<>();
        for (AttemptDtos.AnswerInput input : request.answers()) {
            if (!requestIds.add(input.snapshotId())) {
                throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                        "Một câu hỏi không được xuất hiện hai lần trong cùng lần lưu");
            }
            AttemptQuestionSnapshot snapshot = snapshots.findByIdAndAttemptId(input.snapshotId(), attemptId)
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                            "Câu trả lời không thuộc lượt làm bài này"));
            validateAnswer(snapshot, input);
            AttemptAnswer answer = answers.findByAttemptIdAndSnapshotId(attemptId, snapshot.getId())
                    .orElseGet(() -> new AttemptAnswer(attemptId, snapshot.getId()));
            answer.save(write(input.selectedOptionIds() == null ? List.of() : input.selectedOptionIds()),
                    input.textAnswer(), now);
            answers.save(answer);
        }
        attempt.touch(now);
        attempts.saveAndFlush(attempt);
        return takingResponse(attempt, snapshots.findByAttemptIdOrderByPosition(attemptId),
                answers.findByAttemptId(attemptId));
    }

    @Transactional
    public AttemptDtos.ResultResponse submit(UUID actorId, UUID attemptId, String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Thiếu Idempotency-Key khi nộp bài");
        }
        Attempt attempt = requireOwned(actorId, attemptId);
        if (attempt.getStatus() == AttemptStatus.SUBMITTED) {
            if (idempotencyKey.equals(attempt.getSubmissionKey())) return resultResponse(attempt, Instant.now(clock));
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Lượt làm bài đã được nộp với một khóa idempotency khác");
        }
        if (attempt.getStatus() != AttemptStatus.IN_PROGRESS) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Lượt làm bài không thể nộp ở trạng thái hiện tại");
        }

        Instant now = Instant.now(clock);
        List<AttemptQuestionSnapshot> questionSnapshots = snapshots.findByAttemptIdOrderByPosition(attemptId);
        Map<UUID, AttemptAnswer> saved = new HashMap<>();
        answers.findByAttemptId(attemptId).forEach(answer -> saved.put(answer.getSnapshotId(), answer));
        BigDecimal score = BigDecimal.ZERO;
        BigDecimal maxScore = BigDecimal.ZERO;
        int correctCount = 0;
        for (AttemptQuestionSnapshot snapshot : questionSnapshots) {
            AttemptAnswer answer = saved.computeIfAbsent(snapshot.getId(),
                    ignored -> new AttemptAnswer(attemptId, snapshot.getId()));
            AnswerKey key = read(snapshot.getAnswerKey(), AnswerKey.class);
            List<UUID> selected = read(answer.getSelectedOptionIds(), new TypeReference<>() {});
            boolean correct = ScoringPolicy.isCorrect(snapshot.getQuestionType(), selected, answer.getTextAnswer(),
                    key.correctOptionIds(), key.acceptedAnswers());
            answer.grade(correct, snapshot.getPoints(), now);
            answers.save(answer);
            maxScore = maxScore.add(snapshot.getPoints());
            if (correct) {
                score = score.add(snapshot.getPoints());
                correctCount++;
            }
        }
        attempt.submit(score, maxScore, correctCount, idempotencyKey, now);
        attempts.saveAndFlush(attempt);
        return resultResponse(attempt, now);
    }

    @Transactional(readOnly = true)
    public AttemptDtos.ResultResponse result(UUID actorId, UUID attemptId) {
        Attempt attempt = requireOwned(actorId, attemptId);
        if (attempt.getStatus() != AttemptStatus.SUBMITTED) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Lượt làm bài chưa được nộp");
        }
        return resultResponse(attempt, Instant.now(clock));
    }

    @Transactional(readOnly = true)
    public Page<AttemptDtos.HistoryItem> history(UUID actorId, Pageable pageable) {
        return attempts.findByUserIdOrderByStartedAtDesc(actorId, pageable).map(AttemptDtos.HistoryItem::from);
    }

    private AssignmentPolicyGateway.Policy authorizeAssignment(UUID assignmentId, UUID quizId,
                                                                UUID actorId, Instant now) {
        if (assignmentPolicies == null) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Mô-đun bài tập chưa được cấu hình");
        }
        AssignmentPolicyGateway.Policy policy = assignmentPolicies.authorizeStart(assignmentId, quizId, actorId, now);
        if (policy.opensAt() != null && now.isBefore(policy.opensAt())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Bài tập chưa mở");
        }
        if (policy.dueAt() != null && !now.isBefore(policy.dueAt())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Bài tập đã quá hạn");
        }
        if (policy.maxAttempts() < 1 || policy.answerReleasePolicy() == null) {
            throw new IllegalStateException("Chính sách bài tập không hợp lệ");
        }
        return policy;
    }

    private AttemptQuestionSnapshot snapshot(UUID attemptId, Question question, int position,
                                             boolean shuffleOptions, Random random) {
        List<QuestionOption> questionOptions = new ArrayList<>(options.findByQuestionIdOrderByPosition(question.getId()));
        if (shuffleOptions) Collections.shuffle(questionOptions, random);
        List<SnapshotOption> safeOptions = questionOptions.stream()
                .map(option -> new SnapshotOption(option.getId(), option.getOptionText(),
                        questionOptions.indexOf(option) + 1)).toList();
        List<UUID> correctIds = questionOptions.stream().filter(QuestionOption::isCorrect)
                .map(QuestionOption::getId).toList();
        List<String> accepted = acceptedAnswers.findByQuestionIdOrderByPosition(question.getId()).stream()
                .map(value -> value.getAnswerText()).toList();
        return new AttemptQuestionSnapshot(attemptId, question.getId(), question.getSourceChunkId(), question.getType(),
                question.getPrompt(), question.getExplanation(), question.getPoints(), position,
                write(safeOptions), write(new AnswerKey(correctIds, accepted)));
    }

    private void validateAnswer(AttemptQuestionSnapshot snapshot, AttemptDtos.AnswerInput input) {
        List<UUID> selected = input.selectedOptionIds() == null ? List.of() : input.selectedOptionIds();
        if (new HashSet<>(selected).size() != selected.size()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, "Lựa chọn trả lời bị trùng");
        }
        List<SnapshotOption> validOptions = read(snapshot.getOptionsPayload(), new TypeReference<>() {});
        Set<UUID> validIds = validOptions.stream().map(SnapshotOption::id)
                .collect(java.util.stream.Collectors.toSet());
        if (!validIds.containsAll(selected)) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Lựa chọn không thuộc câu hỏi này");
        }
        if (snapshot.getQuestionType() == QuestionType.SINGLE_CHOICE && selected.size() > 1) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Câu hỏi này chỉ cho phép chọn một đáp án");
        }
        if (snapshot.getQuestionType() == QuestionType.FILL_BLANK && !selected.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Câu điền khuyết không nhận lựa chọn");
        }
        if (snapshot.getQuestionType() != QuestionType.FILL_BLANK
                && input.textAnswer() != null && !input.textAnswer().isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Câu trắc nghiệm không nhận câu trả lời văn bản");
        }
    }

    private AttemptDtos.AttemptResponse takingResponse(Attempt attempt,
                                                       List<AttemptQuestionSnapshot> questionSnapshots,
                                                       List<AttemptAnswer> savedAnswers) {
        List<AttemptDtos.Question> safeQuestions = questionSnapshots.stream().map(snapshot -> {
            List<SnapshotOption> values = read(snapshot.getOptionsPayload(), new TypeReference<>() {});
            return new AttemptDtos.Question(snapshot.getId(), snapshot.getQuestionType(), snapshot.getPrompt(),
                    snapshot.getPoints(), snapshot.getPosition(), values.stream()
                    .map(value -> new AttemptDtos.Option(value.id(), value.text(), value.position())).toList());
        }).toList();
        List<AttemptDtos.SavedAnswer> safeAnswers = savedAnswers.stream().map(answer ->
                new AttemptDtos.SavedAnswer(answer.getSnapshotId(),
                        read(answer.getSelectedOptionIds(), new TypeReference<>() {}), answer.getTextAnswer(),
                        answer.getVersion())).toList();
        return new AttemptDtos.AttemptResponse(attempt.getId(), attempt.getQuizId(), attempt.getAssignmentId(),
                attempt.getStatus(), attempt.getStartedAt(), attempt.getExpiresAt(), attempt.getSubmittedAt(),
                attempt.getVersion(), safeQuestions, safeAnswers);
    }

    private AttemptDtos.ResultResponse resultResponse(Attempt attempt, Instant now) {
        boolean released = attempt.isAllowReview() && attempt.answersMayBeReleased(now);
        List<AttemptDtos.QuestionResult> detail = List.of();
        if (released) {
            Map<UUID, AttemptAnswer> bySnapshot = new LinkedHashMap<>();
            answers.findByAttemptId(attempt.getId()).forEach(answer -> bySnapshot.put(answer.getSnapshotId(), answer));
            detail = snapshots.findByAttemptIdOrderByPosition(attempt.getId()).stream().map(snapshot -> {
                AttemptAnswer answer = bySnapshot.get(snapshot.getId());
                AnswerKey key = read(snapshot.getAnswerKey(), AnswerKey.class);
                return new AttemptDtos.QuestionResult(snapshot.getId(), answer == null ? Boolean.FALSE : answer.getCorrect(),
                        answer == null ? BigDecimal.ZERO : answer.getAwardedPoints(), snapshot.getPoints(),
                        key.correctOptionIds(), key.acceptedAnswers(), snapshot.getExplanation());
            }).toList();
        }
        return new AttemptDtos.ResultResponse(attempt.getId(), attempt.getQuizId(), attempt.getStatus(),
                attempt.isShowScore() ? attempt.getScore() : null,
                attempt.isShowScore() ? attempt.getMaxScore() : null,
                attempt.isShowScore() ? attempt.getPercentage() : null, attempt.isTimedOut(), released,
                attempt.getSubmittedAt(), detail);
    }

    private Attempt requireOwned(UUID actorId, UUID attemptId) {
        return attempts.findByIdAndUserId(attemptId, actorId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy lượt làm bài"));
    }

    private String write(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Không thể lưu dữ liệu câu hỏi", exception);
        }
    }

    private <T> T read(String value, Class<T> type) {
        try {
            return objectMapper.readValue(value, type);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Dữ liệu snapshot bị hỏng", exception);
        }
    }

    private <T> T read(String value, TypeReference<T> type) {
        try {
            return objectMapper.readValue(value, type);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Dữ liệu snapshot bị hỏng", exception);
        }
    }

    record SnapshotOption(UUID id, String text, int position) {}
    record AnswerKey(List<UUID> correctOptionIds, List<String> acceptedAnswers) {
        AnswerKey {
            correctOptionIds = correctOptionIds == null ? List.of() : List.copyOf(correctOptionIds);
            acceptedAnswers = acceptedAnswers == null ? List.of() : List.copyOf(acceptedAnswers);
        }
    }
}
