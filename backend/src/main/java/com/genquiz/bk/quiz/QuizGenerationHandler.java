package com.genquiz.bk.quiz;

import com.genquiz.bk.config.QuizGenerationBatchProperties;
import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobDeferredException;
import com.genquiz.bk.job.JobHandler;
import com.genquiz.bk.job.JobService;
import com.genquiz.bk.job.JobType;
import com.genquiz.bk.rag.RagClient;
import com.genquiz.bk.rag.RagDtos;
import com.genquiz.bk.rag.RagServiceException;
import com.genquiz.bk.source.SourceDocument;
import com.genquiz.bk.source.SourceDocumentRepository;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.IntStream;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Component
public class QuizGenerationHandler implements JobHandler {
    private final QuizService quizzes;
    private final QuizGenerationCommitService commit;
    private final SourceDocumentRepository sources;
    private final ObjectMapper mapper;
    private final RagClient rag;
    private final JobService jobs;
    private final QuizGenerationBatchProperties batchProperties;

    @Autowired
    public QuizGenerationHandler(
            QuizService quizzes,
            QuizGenerationCommitService commit,
            SourceDocumentRepository sources,
            ObjectMapper mapper,
            RagClient rag,
            JobService jobs,
            QuizGenerationBatchProperties batchProperties) {
        this.quizzes = quizzes;
        this.commit = commit;
        this.sources = sources;
        this.mapper = mapper;
        this.rag = rag;
        this.jobs = jobs;
        this.batchProperties = batchProperties;
    }

    QuizGenerationHandler(
            QuizService quizzes,
            QuizGenerationCommitService commit,
            SourceDocumentRepository sources,
            ObjectMapper mapper,
            RagClient rag,
            JobService jobs) {
        this(quizzes, commit, sources, mapper, rag, jobs,
                new QuizGenerationBatchProperties(
                        4, 3, Duration.ofMinutes(5), Duration.ofSeconds(15)));
    }

    @Override
    public JobType type() {
        return JobType.QUIZ_GENERATION;
    }

    @Override
    public String handle(Job job) throws Exception {
        JsonNode payload = mapper.readTree(job.getPayload());
        UUID quizId = UUID.fromString(payload.path("quizId").stringValue());
        quizzes.markGenerating(quizId);
        jobs.progress(job.getId(), 10, "RETRIEVING");
        List<SourceDocument> selected = selectedSources(payload);
        if (selected.stream().anyMatch(source -> source.getRagDocumentId() == null)) {
            throw new IllegalArgumentException("SOURCE_NOT_INDEXED");
        }

        JsonNode countNode = payload.path("questionCounts");
        QuizDtos.QuestionCounts expected = new QuizDtos.QuestionCounts(
                countNode.path("singleChoice").asInt(),
                countNode.path("multipleSelect").asInt(),
                countNode.path("fillBlank").asInt());
        Difficulty quizDifficulty = Difficulty.valueOf(
                payload.path("difficulty").stringValue());
        List<QuizGenerationBatchPlanner.BatchPlan> plans =
                QuizGenerationBatchPlanner.plan(
                        expected, quizDifficulty, batchProperties.batchMaxQuestions());
        String fingerprint = fingerprint(payload, selected);
        QuizGenerationCheckpoint checkpoint = readCheckpoint(
                job.getCheckpointPayload(), fingerprint, plans);
        if (job.getCheckpointPayload() != null
                && "QUEUED".equals(job.getStep())
                && job.getErrorCode() == null) {
            checkpoint = checkpoint.resetIncompleteAttempts();
            saveCheckpoint(job, checkpoint);
        }

        int nextBatch = checkpoint.nextIncompleteIndex();
        if (nextBatch >= 0) {
            checkpoint = generateOneBatch(
                    job, payload, selected, checkpoint, nextBatch);
            if (checkpoint.nextIncompleteIndex() >= 0) {
                int completed = completedQuestionCount(checkpoint);
                jobs.progress(job.getId(), generationProgress(completed, expected.total()),
                        batchStep("WAITING_NEXT_BATCH",
                                checkpoint.nextIncompleteIndex(),
                                checkpoint.batches().size(),
                                completed, expected.total()));
                throw new JobDeferredException(batchProperties.batchSuccessDelay());
            }
        }

        jobs.progress(job.getId(), 85, "VALIDATING_ALL_BATCHES");
        RagDtos.GeneratedQuiz generated = aggregate(checkpoint);
        List<QuizDtos.GroundedQuestion> questions = IntStream.range(
                        0, generated.questions().size())
                .mapToObj(index -> mapQuestion(
                        generated.questions().get(index),
                        resolveQuestionDifficulty(
                                generated.questions().get(index).difficulty(),
                                quizDifficulty, index, generated.questions().size())))
                .toList();
        jobs.progress(job.getId(), 95, "COMMITTING");
        commit.replaceGroundedAndComplete(quizId, questions, expected);
        return mapper.writeValueAsString(Map.of(
                "quizId", quizId,
                "questionCount", questions.size(),
                "batchCount", checkpoint.batches().size(),
                "model", generated.model(),
                "usage", generated.usage()));
    }

    private QuizGenerationCheckpoint generateOneBatch(
            Job job,
            JsonNode payload,
            List<SourceDocument> selected,
            QuizGenerationCheckpoint checkpoint,
            int batchIndex) throws Exception {
        QuizGenerationCheckpoint.BatchState batch =
                checkpoint.batches().get(batchIndex);
        checkpoint = checkpoint.recordAttempt(batchIndex);
        saveCheckpoint(job, checkpoint);
        batch = checkpoint.batches().get(batchIndex);
        int completed = completedQuestionCount(checkpoint);
        int totalQuestions = checkpoint.batches().stream()
                .mapToInt(value -> count(value.counts())).sum();
        jobs.progress(job.getId(), generationProgress(completed, totalQuestions),
                batchStep("GENERATING_BATCH", batchIndex,
                        checkpoint.batches().size(), completed, totalQuestions));

        RagDtos.GenerateRequest request = new RagDtos.GenerateRequest(
                selected.stream().map(SourceDocument::getRagDocumentId).toList(),
                payload.path("title").stringValue(),
                payload.path("difficulty").stringValue(),
                batch.counts(),
                batchIndex,
                checkpoint.batches().size(),
                batch.difficultyPlan(),
                checkpoint.excludedPrompts());
        try {
            RagDtos.GeneratedQuiz generated =
                    rag.generate(job.getSubjectUserId(), request);
            checkpoint = checkpoint.complete(batchIndex, generated);
            saveCheckpoint(job, checkpoint);
            return checkpoint;
        } catch (RagServiceException exception) {
            checkpoint = checkpoint.fail(
                    batchIndex, exception.code(), exception.upstreamRequestId());
            saveCheckpoint(job, checkpoint);
            jobs.progress(job.getId(), generationProgress(completed, totalQuestions),
                    batchStep(exception.retryable()
                                    ? "WAITING_GEMINI_RETRY" : "BATCH_FAILED",
                            batchIndex, checkpoint.batches().size(),
                            completed, totalQuestions));
            if (exception.retryable()
                    && checkpoint.batches().get(batchIndex).attempts()
                    >= batchProperties.batchMaxAttempts()) {
                throw new RagServiceException(
                        exception.code(),
                        exception.getMessage(),
                        false,
                        null,
                        exception.upstreamRequestId(),
                        exception);
            }
            throw exception;
        }
    }

    private List<SourceDocument> selectedSources(JsonNode payload) {
        List<SourceDocument> selected = new ArrayList<>();
        payload.path("sourceIds").forEach(node -> selected.add(
                sources.findById(UUID.fromString(node.stringValue()))
                        .orElseThrow(() -> new IllegalArgumentException(
                                "Không tìm thấy nguồn tài liệu."))));
        return selected;
    }

    private QuizGenerationCheckpoint readCheckpoint(
            String raw,
            String fingerprint,
            List<QuizGenerationBatchPlanner.BatchPlan> plans) {
        if (raw != null && !raw.isBlank()) {
            try {
                QuizGenerationCheckpoint checkpoint =
                        mapper.readValue(raw, QuizGenerationCheckpoint.class);
                if (checkpoint.matches(fingerprint, plans.size())) return checkpoint;
            } catch (Exception ignored) {
                // A stale/legacy checkpoint is safely replaced by the deterministic plan.
            }
        }
        return QuizGenerationCheckpoint.create(fingerprint, plans);
    }

    private void saveCheckpoint(Job job, QuizGenerationCheckpoint checkpoint)
            throws Exception {
        String value = mapper.writeValueAsString(checkpoint);
        jobs.checkpoint(job.getId(), value);
    }

    private RagDtos.GeneratedQuiz aggregate(QuizGenerationCheckpoint checkpoint) {
        List<RagDtos.GeneratedQuestion> questions = checkpoint.generatedQuestions();
        Map<String, Integer> usage = new LinkedHashMap<>();
        String model = null;
        for (QuizGenerationCheckpoint.BatchState batch : checkpoint.batches()) {
            if (batch.generated() == null) {
                throw new IllegalStateException("Quiz batch chưa hoàn tất.");
            }
            if (model == null) model = batch.generated().model();
            batch.generated().usage().forEach(
                    (key, value) -> usage.merge(key, value, Integer::sum));
        }
        return new RagDtos.GeneratedQuiz(
                questions, model == null ? "unknown" : model, Map.copyOf(usage));
    }

    private QuizDtos.GroundedQuestion mapQuestion(
            RagDtos.GeneratedQuestion value, Difficulty difficulty) {
        QuestionType type = QuestionType.valueOf(value.type());
        List<QuizDtos.OptionRequest> options = value.options() == null
                ? List.of()
                : value.options().stream().map(option ->
                new QuizDtos.OptionRequest(option.text(), option.correct())).toList();
        List<String> accepted = value.acceptedAnswers() == null
                ? List.of() : value.acceptedAnswers();
        List<QuizDtos.CitationRequest> citations = new ArrayList<>();
        value.questionCitations().forEach(citation -> citations.add(
                new QuizDtos.CitationRequest(
                        citation.chunkId(), CitationRole.QUESTION,
                        citation.evidenceQuote())));
        value.answerCitations().forEach(citation -> citations.add(
                new QuizDtos.CitationRequest(
                        citation.chunkId(), CitationRole.ANSWER,
                        citation.evidenceQuote())));
        value.explanationCitations().forEach(citation -> citations.add(
                new QuizDtos.CitationRequest(
                        citation.chunkId(), CitationRole.EXPLANATION,
                        citation.evidenceQuote())));
        if (citations.isEmpty()) {
            throw new IllegalArgumentException("GROUNDING_CITATION_REQUIRED");
        }
        UUID primary = citations.get(0).sourceChunkId();
        var question = new QuizDtos.QuestionRequest(
                type, value.prompt(), value.explanation(), BigDecimal.ONE,
                difficulty, primary, options, accepted);
        return new QuizDtos.GroundedQuestion(question, citations);
    }

    static Difficulty resolveQuestionDifficulty(
            String generatedDifficulty,
            Difficulty quizDifficulty,
            int index,
            int total) {
        if (generatedDifficulty != null && !generatedDifficulty.isBlank()) {
            Difficulty value;
            try {
                value = Difficulty.valueOf(generatedDifficulty);
            } catch (IllegalArgumentException exception) {
                throw new IllegalArgumentException(
                        "QUESTION_DIFFICULTY_INVALID", exception);
            }
            if (value == Difficulty.MIXED) {
                throw new IllegalArgumentException(
                        "QUESTION_DIFFICULTY_INVALID");
            }
            return value;
        }
        if (quizDifficulty != Difficulty.MIXED) return quizDifficulty;
        if (total == 1) return Difficulty.MEDIUM;
        if (total == 2) return index == 0 ? Difficulty.EASY : Difficulty.HARD;
        return switch (index % 3) {
            case 0 -> Difficulty.EASY;
            case 1 -> Difficulty.MEDIUM;
            default -> Difficulty.HARD;
        };
    }

    private String fingerprint(
            JsonNode payload, List<SourceDocument> selected) throws Exception {
        StringBuilder value = new StringBuilder(
                mapper.writeValueAsString(payload));
        selected.stream().sorted(Comparator.comparing(SourceDocument::getId))
                .forEach(source -> value.append('|').append(source.getId())
                        .append(':').append(source.getRagDocumentId())
                        .append(':').append(source.getIndexedAt())
                        .append(':').append(source.getChunkCount()));
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(
                        value.toString().getBytes(StandardCharsets.UTF_8)));
    }

    private static int completedQuestionCount(
            QuizGenerationCheckpoint checkpoint) {
        return checkpoint.batches().stream()
                .filter(batch -> batch.generated() != null)
                .mapToInt(batch -> batch.generated().questions().size())
                .sum();
    }

    private static int generationProgress(int completed, int total) {
        if (total <= 0) return 10;
        return 10 + (int) Math.floor(70.0 * completed / total);
    }

    private static int count(RagDtos.Counts counts) {
        return counts.singleChoice()
                + counts.multipleSelect()
                + counts.fillBlank();
    }

    private static String batchStep(
            String stage,
            int zeroBasedBatch,
            int totalBatches,
            int completedQuestions,
            int totalQuestions) {
        return stage + "_" + (zeroBasedBatch + 1)
                + "_OF_" + totalBatches
                + "_COMPLETED_" + completedQuestions
                + "_OF_" + totalQuestions;
    }
}
