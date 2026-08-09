package com.genquiz.bk.job;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import tools.jackson.databind.ObjectMapper;

class JobEventTest {
    @Test
    void timelineDtoAlwaysSerializesNullableContractFields() {
        JsonInclude annotation = JobEventDtos.Item.class.getAnnotation(JsonInclude.class);

        assertEquals(JsonInclude.Include.ALWAYS, annotation.value());
    }

    @Test
    void createsAUserSafeTimelineEvent() {
        UUID jobId = UUID.randomUUID();
        Instant occurredAt = Instant.parse("2026-07-29T10:15:30Z");

        JobEvent event = new JobEvent(
                jobId,
                JobEventLevel.WARNING,
                "FALLBACK_STARTED",
                "Gemini không thể hoàn tất yêu cầu. Đang chuyển sang Ollama Qwen.",
                35,
                "ollama",
                0,
                2,
                "rag-request-1",
                "{}",
                occurredAt);

        assertEquals(jobId, event.getJobId());
        assertEquals(JobEventLevel.WARNING, event.getLevel());
        assertEquals("FALLBACK_STARTED", event.getCode());
        assertEquals(occurredAt, event.getOccurredAt());
    }

    @Test
    void preservesSafeCognitiveSummaryAndStripsQuestionContent() throws Exception {
        JobEventRepository repository = mock(JobEventRepository.class);
        when(repository.findFirstByJobIdOrderByIdDesc(org.mockito.ArgumentMatchers.any()))
                .thenReturn(Optional.empty());
        ObjectMapper mapper = new ObjectMapper();
        JobEventService service = new JobEventService(
                repository,
                mock(JobRepository.class),
                mapper,
                Clock.fixed(Instant.parse("2026-08-07T13:35:42Z"), ZoneOffset.UTC));
        var metadata = mapper.readTree("""
                {"acceptedQuestions":6,"rejectedQuestions":4,
                 "failureDistribution":{"NOVEL_SCENARIO_REQUIRED":3},
                 "questionText":"Nội dung không được lưu"}
                """);

        service.record(
                UUID.randomUUID(), JobEventLevel.WARNING,
                "COGNITIVE_VALIDATION_SUMMARY", "6/10 câu đạt.", 50,
                null, 0, null, null, metadata);

        ArgumentCaptor<JobEvent> captured = ArgumentCaptor.forClass(JobEvent.class);
        verify(repository).save(captured.capture());
        var stored = mapper.readTree(captured.getValue().getMetadata());
        assertEquals(6, stored.path("acceptedQuestions").asInt());
        assertEquals(3, stored.path("failureDistribution")
                .path("NOVEL_SCENARIO_REQUIRED").asInt());
        assertFalse(stored.has("questionText"));
    }

    @Test
    void preservesOnlySafeValidationDetailsForTheTimeline() throws Exception {
        JobEventRepository repository = mock(JobEventRepository.class);
        when(repository.findFirstByJobIdOrderByIdDesc(org.mockito.ArgumentMatchers.any()))
                .thenReturn(Optional.empty());
        ObjectMapper mapper = new ObjectMapper();
        JobEventService service = new JobEventService(
                repository,
                mock(JobRepository.class),
                mapper,
                Clock.systemUTC());
        var metadata = mapper.readTree("""
                {"details":[
                  {"field":"acceptedQuestions","type":"list_type",
                   "message":"Input should be a valid list","secret":"must-not-be-stored"}
                ]}
                """);

        service.record(
                UUID.randomUUID(), JobEventLevel.ERROR,
                "VALIDATION_ERROR", "Dữ liệu gửi lên không hợp lệ.", null,
                null, null, null, "rag-request-1", metadata);

        ArgumentCaptor<JobEvent> captured = ArgumentCaptor.forClass(JobEvent.class);
        verify(repository).save(captured.capture());
        var stored = mapper.readTree(captured.getValue().getMetadata());
        assertEquals("acceptedQuestions", stored.path("validationErrors")
                .path(0).path("field").stringValue());
        assertFalse(stored.path("validationErrors").path(0).has("secret"));
    }

    @Test
    void preservesCitationSummaryWithoutEvidenceText() throws Exception {
        JobEventRepository repository = mock(JobEventRepository.class);
        when(repository.findFirstByJobIdOrderByIdDesc(org.mockito.ArgumentMatchers.any()))
                .thenReturn(Optional.empty());
        ObjectMapper mapper = new ObjectMapper();
        JobEventService service = new JobEventService(
                repository, mock(JobRepository.class), mapper, Clock.systemUTC());
        var metadata = mapper.readTree("""
                {"semanticSameSource":4,"semanticCrossSource":1,"dropped":2,
                 "invalidCitations":3,"details":[
                   {"reason":"INVALID_CITATION_QUOTE","questionIndex":2,
                    "citationRole":"ANSWER","sourceId":"S4",
                    "evidenceQuote":"must-not-be-stored"}
                 ]}
                """);

        service.record(
                UUID.randomUUID(), JobEventLevel.WARNING,
                "CITATION_VALIDATION_SUMMARY", "Đã đối chiếu nguồn.", 70,
                null, 0, null, "rag-request-2", metadata);

        ArgumentCaptor<JobEvent> captured = ArgumentCaptor.forClass(JobEvent.class);
        verify(repository).save(captured.capture());
        var stored = mapper.readTree(captured.getValue().getMetadata());
        assertEquals(5, stored.path("semanticSameSource").asInt()
                + stored.path("semanticCrossSource").asInt());
        assertEquals("ANSWER", stored.path("citationErrors")
                .path(0).path("citationRole").stringValue());
        assertFalse(stored.toString().contains("must-not-be-stored"));
    }

    @Test
    void preservesSafeInternalFailureStageAndDiagnosticId() throws Exception {
        JobEventRepository repository = mock(JobEventRepository.class);
        when(repository.findFirstByJobIdOrderByIdDesc(org.mockito.ArgumentMatchers.any()))
                .thenReturn(Optional.empty());
        ObjectMapper mapper = new ObjectMapper();
        JobEventService service = new JobEventService(
                repository, mock(JobRepository.class), mapper, Clock.systemUTC());
        var metadata = mapper.readTree("""
                {"stage":"MATCHING_CITATIONS","errorId":"rag-error-456",
                 "exceptionMessage":"must-not-be-stored"}
                """);

        service.record(
                UUID.randomUUID(), JobEventLevel.ERROR,
                "RAG_INTERNAL_ERROR", "RAG gặp lỗi nội bộ.", 70,
                null, 0, null, "job-1", metadata);

        ArgumentCaptor<JobEvent> captured = ArgumentCaptor.forClass(JobEvent.class);
        verify(repository).save(captured.capture());
        var stored = mapper.readTree(captured.getValue().getMetadata());
        assertEquals("MATCHING_CITATIONS", stored.path("stage").stringValue());
        assertEquals("rag-error-456", stored.path("errorId").stringValue());
        assertFalse(stored.has("exceptionMessage"));
    }
}
