package com.genquiz.bk.job;

import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Service
public class JobEventService {
    private final JobEventRepository events;
    private final JobRepository jobs;
    private final ObjectMapper mapper;
    private final Clock clock;

    @Autowired
    public JobEventService(
            JobEventRepository events,
            JobRepository jobs,
            ObjectMapper mapper) {
        this(events, jobs, mapper, Clock.systemUTC());
    }

    JobEventService(
            JobEventRepository events,
            JobRepository jobs,
            ObjectMapper mapper,
            Clock clock) {
        this.events = events;
        this.jobs = jobs;
        this.mapper = mapper;
        this.clock = clock;
    }

    @Transactional
    public void record(
            UUID jobId,
            JobEventLevel level,
            String code,
            String message,
            Integer progress,
            String provider,
            Integer batchIndex,
            Integer partIndex,
            String requestId,
            JsonNode metadata) {
        JobEvent previous = events.findFirstByJobIdOrderByIdDesc(jobId).orElse(null);
        if (previous != null
                && previous.getCode().equals(code)
                && previous.getMessage().equals(message)
                && java.util.Objects.equals(previous.getProgress(), progress)
                && java.util.Objects.equals(previous.getProvider(), provider)
                && java.util.Objects.equals(previous.getBatchIndex(), batchIndex)
                && java.util.Objects.equals(previous.getPartIndex(), partIndex)) {
            return;
        }
        String safeMetadata = metadata == null ? "{}" : safeMetadata(metadata).toString();
        events.save(new JobEvent(
                jobId,
                level,
                code,
                message,
                progress,
                provider,
                batchIndex,
                partIndex,
                requestId,
                safeMetadata,
                Instant.now(clock)));
        events.flush();
    }

    @Transactional(readOnly = true)
    public JobEventDtos.Page listOwned(
            UUID actorId, UUID jobId, long afterId, int limit) {
        jobs.findByIdAndSubjectUserId(jobId, actorId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Không tìm thấy tác vụ"));
        int safeLimit = Math.max(1, Math.min(500, limit));
        List<JobEvent> found = events.findByJobIdAndIdGreaterThanOrderByIdAsc(
                jobId, Math.max(0, afterId), PageRequest.of(0, safeLimit + 1));
        boolean hasMore = found.size() > safeLimit;
        List<JobEvent> page = hasMore ? found.subList(0, safeLimit) : found;
        List<JobEventDtos.Item> items = page.stream()
                .map(event -> JobEventDtos.Item.from(event, mapper))
                .toList();
        long cursor = items.isEmpty() ? Math.max(0, afterId)
                : items.get(items.size() - 1).id();
        return new JobEventDtos.Page(items, cursor, hasMore);
    }

    private JsonNode safeMetadata(JsonNode source) {
        var safe = mapper.createObjectNode();
        for (String field : List.of(
                "stage", "totalParts", "requestedQuestions", "validQuestions",
                "duplicateQuestions", "retryable", "retryAfterSeconds",
                "fallbackFrom", "totalQuestions", "completedQuestions",
                "generatedQuestions", "acceptedQuestions", "rejectedQuestions",
                "repairRound", "planSlotId", "requestedCognitiveLevel",
                "exactOrNormalized", "lexical", "semanticSameSource",
                "semanticCrossSource", "dropped", "invalidCitations",
                "invalidQuestions", "errorId", "degradedErrorCode")) {
            JsonNode value = source.get(field);
            if (value != null && (value.isBoolean() || value.isNumber() || value.isString())) {
                safe.set(field, value);
            }
        }
        JsonNode distribution = source.get("failureDistribution");
        if (distribution != null && distribution.isObject()) {
            var safeDistribution = mapper.createObjectNode();
            for (String reason : List.of(
                    "LEVEL_MISMATCH", "PLAN_SLOT_MISMATCH", "QUESTION_TYPE_MISMATCH",
                    "MISSING_COMPLEXITY_PROFILE", "INVALID_COMPLEXITY_PROFILE",
                    "CONCEPTS_USED_COUNT_MISMATCH", "CONCEPT_COUNT_OUT_OF_RANGE",
                    "REASONING_STEPS_OUT_OF_RANGE", "NOVEL_SCENARIO_REQUIRED",
                    "NOVEL_SCENARIO_NOT_ALLOWED", "DIRECT_ANSWER_REQUIRED",
                    "DIRECT_ANSWER_NOT_ALLOWED", "COMPARISON_REQUIRED",
                    "COMPARISON_NOT_ALLOWED", "SCORE_OUT_OF_RANGE",
                    "SCENARIO_NOT_NOVEL", "L1_ANSWER_NOT_IN_EVIDENCE")) {
                JsonNode count = distribution.get(reason);
                if (count != null && count.isIntegralNumber() && count.asInt() >= 0) {
                    safeDistribution.set(reason, count);
                }
            }
            if (!safeDistribution.isEmpty()) safe.set("failureDistribution", safeDistribution);
        }
        JsonNode details = source.get("details");
        if (details != null && details.isArray()) {
            var safeErrors = mapper.createArrayNode();
            for (JsonNode detail : details) {
                if (!detail.isObject()) continue;
                String field = boundedText(detail, "field", 160);
                String type = boundedText(detail, "type", 100);
                String message = boundedText(detail, "message", 500);
                if (field == null || type == null || message == null) continue;
                var safeError = mapper.createObjectNode();
                safeError.put("field", field);
                safeError.put("type", type);
                safeError.put("message", message);
                safeErrors.add(safeError);
            }
            if (!safeErrors.isEmpty()) safe.set("validationErrors", safeErrors);
            var safeCitations = mapper.createArrayNode();
            for (JsonNode detail : details) {
                if (!detail.isObject()
                        || !"INVALID_CITATION_QUOTE".equals(
                        detail.path("reason").stringValue(""))) continue;
                JsonNode questionIndex = detail.get("questionIndex");
                String role = boundedText(detail, "citationRole", 32);
                String sourceId = boundedText(detail, "sourceId", 32);
                if (questionIndex == null || !questionIndex.isIntegralNumber()
                        || role == null || sourceId == null) continue;
                var safeCitation = mapper.createObjectNode();
                safeCitation.put("questionIndex", questionIndex.asInt());
                safeCitation.put("citationRole", role);
                safeCitation.put("sourceId", sourceId);
                safeCitations.add(safeCitation);
            }
            if (!safeCitations.isEmpty()) safe.set("citationErrors", safeCitations);
        }
        return safe;
    }

    private static String boundedText(JsonNode source, String field, int maxLength) {
        JsonNode value = source.get(field);
        if (value == null || !value.isString()) return null;
        String text = value.stringValue();
        if (text == null || text.isBlank()) return null;
        return text.length() <= maxLength ? text : text.substring(0, maxLength);
    }
}
