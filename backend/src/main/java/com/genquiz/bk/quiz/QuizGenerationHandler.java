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
import java.util.concurrent.atomic.AtomicReference;
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
                        20, 3, Duration.ofMinutes(5), Duration.ofSeconds(15)));
    }

    @Override
    public JobType type() {
        return JobType.QUIZ_GENERATION;
    }

    @Override
    public String handle(Job job) throws Exception {
        JsonNode payload = mapper.readTree(job.getPayload());
        UUID quizId = UUID.fromString(payload.path("quizId").stringValue());
        QuizGenerationOperation operation = QuizGenerationOperation.valueOf(
                payload.path("operation").stringValue("CREATE"));
        if (operation == QuizGenerationOperation.CREATE) {
            quizzes.markGenerating(quizId);
        }
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
        CognitiveMode cognitiveMode = payload.hasNonNull("cognitiveMode")
                ? CognitiveMode.valueOf(payload.path("cognitiveMode").stringValue())
                : legacyMode(Difficulty.valueOf(payload.path("difficulty").stringValue()));
        List<QuizGenerationBatchPlanner.BatchPlan> plans =
                QuizGenerationBatchPlanner.plan(
                        expected, cognitiveMode, batchProperties.batchMaxQuestions());
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
                        resolveCognitiveLevel(generated.questions().get(index),
                                plans.stream().flatMap(plan -> plan.levels().stream()).toList().get(index))))
                .toList();
        jobs.progress(job.getId(), 95, "COMMITTING");
        AiValidationStatus generatedStatus = validationStatus(generated);
        List<QuizDtos.AiValidationWarning> generatedWarnings = validationWarnings(generated);
        boolean hasQualityWarnings = generatedStatus == AiValidationStatus.WARNING
                || !generatedWarnings.isEmpty();
        if (operation == QuizGenerationOperation.APPEND) {
            if (hasQualityWarnings) {
                commit.appendGroundedAndComplete(
                        quizId, questions, expected,
                        payload.path("baseQuizVersion").asLong(),
                        payload.path("baseQuestionCount").asLong(),
                        payload.path("baseQuestionFingerprint").stringValue(),
                        generatedStatus, generatedWarnings);
            } else {
                commit.appendGroundedAndComplete(
                        quizId, questions, expected,
                        payload.path("baseQuizVersion").asLong(),
                        payload.path("baseQuestionCount").asLong(),
                        payload.path("baseQuestionFingerprint").stringValue());
            }
        } else {
            if (hasQualityWarnings) {
                commit.replaceGroundedAndComplete(
                        quizId, questions, expected, generatedStatus, generatedWarnings);
            } else {
                commit.replaceGroundedAndComplete(quizId, questions, expected);
            }
        }
        return mapper.writeValueAsString(Map.of(
                "quizId", quizId,
                "requestedCount", expected.total(),
                "savedCount", questions.size(),
                "warningCount", nullableInt(generated.warningCount()),
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
        rag.requireQuizGenerationContract();
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
                cognitiveMode(payload).name(),
                batch.counts(),
                batchIndex,
                checkpoint.batches().size(),
                null,
                questionPlan(batch),
                excludedPrompts(payload, checkpoint),
                batch.partialQuestions() == null
                        ? mapper.createArrayNode()
                        : batch.partialQuestions());
        AtomicReference<QuizGenerationCheckpoint> checkpointRef =
                new AtomicReference<>(checkpoint);
        try {
            RagDtos.GeneratedQuiz generated =
                    rag.generateStreaming(
                            job.getSubjectUserId(), job.getId(), request,
                            acceptedQuestions -> {
                                QuizGenerationCheckpoint updated =
                                        checkpointRef.get().partial(
                                                batchIndex, acceptedQuestions);
                                try {
                                    saveCheckpoint(job, updated);
                                } catch (Exception exception) {
                                    throw new IllegalStateException(
                                            "Không thể lưu checkpoint Cognitive.", exception);
                                }
                                checkpointRef.set(updated);
                            });
            generated = checkpointRef.get().restorePartialAccounting(
                    batchIndex, generated);
            checkpoint = checkpointRef.get().complete(batchIndex, generated);
            saveCheckpoint(job, checkpoint);
            return checkpoint;
        } catch (RagServiceException exception) {
            checkpoint = checkpointRef.get();
            checkpoint = checkpoint.fail(
                    batchIndex, exception.code(), exception.upstreamRequestId());
            saveCheckpoint(job, checkpoint);
            jobs.progress(job.getId(), generationProgress(completed, totalQuestions),
                    batchStep(retryStage(exception.code(), exception.retryable()),
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

    static String retryStage(String errorCode, boolean retryable) {
        if (!retryable) return "BATCH_FAILED";
        return switch (errorCode) {
            case "COGNITIVE_CONSTRAINT_VIOLATION" -> "WAITING_COGNITIVE_RETRY";
            case "INVALID_CITATION_QUOTE" -> "WAITING_CITATION_RETRY";
            case "RAG_TRANSIENT_ERROR", "RAG_STREAM_INTERRUPTED",
                    "RAG_STREAM_FAILED", "RAG_STREAM_READ_TIMEOUT",
                    "RAG_UNAVAILABLE" -> "WAITING_RAG_RETRY";
            default -> "WAITING_GEMINI_RETRY";
        };
    }

    private List<String> excludedPrompts(
            JsonNode payload, QuizGenerationCheckpoint checkpoint) {
        var prompts = new ArrayList<String>();
        payload.path("existingPrompts")
                .forEach(value -> prompts.add(value.stringValue()));
        prompts.addAll(checkpoint.excludedPrompts());
        return List.copyOf(prompts);
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
        List<RagDtos.QuizValidationWarning> warnings = checkpoint.batches().stream()
                .map(QuizGenerationCheckpoint.BatchState::generated)
                .filter(java.util.Objects::nonNull)
                .flatMap(value -> value.validationWarnings() == null
                        ? java.util.stream.Stream.empty()
                        : value.validationWarnings().stream())
                .toList();
        int requestedCount = checkpoint.batches().stream()
                .map(QuizGenerationCheckpoint.BatchState::generated)
                .filter(java.util.Objects::nonNull)
                .mapToInt(value -> value.requestedCount() == null
                        ? (value.questions() == null ? 0 : value.questions().size())
                        : value.requestedCount()).sum();
        int warningCount = (int) questions.stream()
                .filter(value -> "WARNING".equals(value.validationStatus())).count();
        return new RagDtos.GeneratedQuiz(
                questions, model == null ? "unknown" : model, Map.copyOf(usage),
                warningCount > 0 ? "WARNING" : "VERIFIED", warnings,
                requestedCount == 0 ? questions.size() : requestedCount,
                questions.size(), warningCount);
    }

    private QuizDtos.GroundedQuestion mapQuestion(
            RagDtos.GeneratedQuestion value, CognitiveLevel level) {
        QuestionType type = QuestionType.valueOf(value.type());
        List<QuizDtos.OptionRequest> options = value.options() == null
                ? List.of()
                : value.options().stream().map(option ->
                new QuizDtos.OptionRequest(option.text(), option.correct())).toList();
        List<String> accepted = value.acceptedAnswers() == null
                ? List.of() : value.acceptedAnswers();
        List<QuizDtos.CitationRequest> citations = new ArrayList<>();
        safe(value.questionCitations()).forEach(citation -> citations.add(
                new QuizDtos.CitationRequest(
                        citation.chunkId(), CitationRole.QUESTION,
                        citation.evidenceQuote(), citation.documentId(), citation.chunkIndex(),
                        citation.pageNumber(), citation.slideNumber(), citation.heading(),
                        citation.chunkText(), citation.rawText(), citation.mathEnhanced(),
                        citation.snapshotFingerprint())));
        safe(value.answerCitations()).forEach(citation -> citations.add(
                new QuizDtos.CitationRequest(
                        citation.chunkId(), CitationRole.ANSWER,
                        citation.evidenceQuote(), citation.documentId(), citation.chunkIndex(),
                        citation.pageNumber(), citation.slideNumber(), citation.heading(),
                        citation.chunkText(), citation.rawText(), citation.mathEnhanced(),
                        citation.snapshotFingerprint())));
        safe(value.explanationCitations()).forEach(citation -> citations.add(
                new QuizDtos.CitationRequest(
                        citation.chunkId(), CitationRole.EXPLANATION,
                        citation.evidenceQuote(), citation.documentId(), citation.chunkIndex(),
                        citation.pageNumber(), citation.slideNumber(), citation.heading(),
                        citation.chunkText(), citation.rawText(), citation.mathEnhanced(),
                        citation.snapshotFingerprint())));
        UUID primary = citations.isEmpty() ? null : citations.get(0).sourceChunkId();
        RagDtos.ComplexityProfile generatedProfile = value.complexityProfile();
        CognitiveProfile profile = generatedProfile == null
                ? new CognitiveProfile(0, 0, false, false, false, List.of(), null, false)
                : new CognitiveProfile(generatedProfile.conceptCount(), generatedProfile.reasoningStepCount(),
                generatedProfile.requiresNovelScenario(), generatedProfile.answerDirectlyPresent(),
                generatedProfile.requiresComparison(), generatedProfile.conceptsUsed(),
                generatedProfile.novelScenarioSummary(), value.complexityVerified());
        if (profile.verified()) CognitivePolicy.validate(level, profile);
        var question = new QuizDtos.QuestionRequest(
                type, value.prompt(), value.explanation(), BigDecimal.ONE,
                null, level, profile, primary, options, accepted);
        List<QuizDtos.AiValidationWarning> warnings = value.validationWarnings() == null
                ? List.of()
                : value.validationWarnings().stream().map(item ->
                new QuizDtos.AiValidationWarning(
                        item.code(), item.role(), item.expected(), item.actual(),
                        item.sourceId(), item.message())).toList();
        AiValidationStatus status = "WARNING".equals(value.validationStatus())
                ? AiValidationStatus.WARNING : AiValidationStatus.VERIFIED;
        return new QuizDtos.GroundedQuestion(question, citations, status, warnings);
    }

    private static <T> List<T> safe(List<T> values) {
        return values == null ? List.of() : values;
    }

    private static int nullableInt(Integer value) {
        return value == null ? 0 : value;
    }

    private static AiValidationStatus validationStatus(RagDtos.GeneratedQuiz generated) {
        return "WARNING".equals(generated.validationStatus())
                ? AiValidationStatus.WARNING : AiValidationStatus.VERIFIED;
    }

    private static List<QuizDtos.AiValidationWarning> validationWarnings(
            RagDtos.GeneratedQuiz generated) {
        if (generated.validationWarnings() == null) return List.of();
        return generated.validationWarnings().stream().map(item ->
                new QuizDtos.AiValidationWarning(
                        item.code(), item.role(), item.expected(), item.actual(),
                        item.sourceId(), item.message())).toList();
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

    private static CognitiveLevel resolveCognitiveLevel(
            RagDtos.GeneratedQuestion generated, CognitiveLevel planned) {
        if (generated.cognitiveLevel() == null || generated.cognitiveLevel().isBlank()) return planned;
        CognitiveLevel actual;
        try {
            actual = CognitiveLevel.valueOf(generated.cognitiveLevel());
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("COGNITIVE_LEVEL_INVALID", exception);
        }
        if (actual != planned) throw new IllegalArgumentException("COGNITIVE_PLAN_INVALID");
        return actual;
    }

    private static CognitiveMode legacyMode(Difficulty difficulty) {
        return switch (difficulty) {
            case EASY -> CognitiveMode.L1;
            case MEDIUM -> CognitiveMode.L3;
            case HARD -> CognitiveMode.L5;
            case MIXED -> CognitiveMode.BALANCED;
        };
    }

    private static CognitiveMode cognitiveMode(JsonNode payload) {
        return payload.hasNonNull("cognitiveMode")
                ? CognitiveMode.valueOf(payload.path("cognitiveMode").stringValue())
                : legacyMode(Difficulty.valueOf(payload.path("difficulty").stringValue()));
    }

    private static List<RagDtos.QuestionPlan> questionPlan(QuizGenerationCheckpoint.BatchState batch) {
        List<String> types = new ArrayList<>();
        int[] remaining = {batch.counts().singleChoice(), batch.counts().multipleSelect(),
                batch.counts().fillBlank()};
        String[] names = {"SINGLE_CHOICE", "MULTIPLE_SELECT", "FILL_BLANK"};
        int cursor = 0;
        while (types.size() < batch.difficultyPlan().size()) {
            for (int offset = 0; offset < 3; offset++) {
                int candidate = (cursor + offset) % 3;
                if (remaining[candidate] > 0) {
                    types.add(names[candidate]);
                    remaining[candidate]--;
                    cursor = (candidate + 1) % 3;
                    break;
                }
            }
        }
        return IntStream.range(0, batch.difficultyPlan().size()).mapToObj(index -> {
            CognitiveLevel level = CognitiveLevel.valueOf(batch.difficultyPlan().get(index));
            return new RagDtos.QuestionPlan("B" + (batch.index() + 1) + "Q" + (index + 1),
                    types.get(index), level.name(), constraint(level));
        }).toList();
    }

    private static RagDtos.CognitiveConstraint constraint(CognitiveLevel level) {
        return switch (level) {
            case L1 -> new RagDtos.CognitiveConstraint("L1", 1, 1, 0, 0, false, true, false, 1, 2);
            case L2 -> new RagDtos.CognitiveConstraint("L2", 1, 2, 1, 1, false, false, false, 3, 4);
            case L3 -> new RagDtos.CognitiveConstraint("L3", 1, 2, 1, 2, true, false, false, 5, 7);
            case L4 -> new RagDtos.CognitiveConstraint("L4", 2, 4, 2, 3, true, false, true, 8, 10);
            case L5 -> new RagDtos.CognitiveConstraint("L5", 3, 6, 3, 5, true, false, true, 11, null);
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
