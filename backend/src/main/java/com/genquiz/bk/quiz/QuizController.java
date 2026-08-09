package com.genquiz.bk.quiz;

import com.genquiz.bk.topic.ActorIdentityService;
import jakarta.validation.Valid;
import java.net.URI;
import java.security.Principal;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.genquiz.bk.security.CurrentUser;
import org.springframework.web.bind.annotation.RequestParam;
import com.genquiz.bk.source.SourceDtos;
import com.genquiz.bk.source.SourcePresentationService;
import java.util.List;
import com.genquiz.bk.job.JobDtos;
import com.genquiz.bk.job.JobService;

@RestController
@RequestMapping("/api/quizzes")
public class QuizController {
    private final QuizService service;
    private final ActorIdentityService actors;
    private final CurrentUser currentUser;
    private final SourcePresentationService sourcePresentation;
    private final JobService jobs;

    public QuizController(QuizService service, ActorIdentityService actors, CurrentUser currentUser,
                          SourcePresentationService sourcePresentation, JobService jobs) {
        this.service = service;
        this.actors = actors;
        this.currentUser = currentUser;
        this.sourcePresentation = sourcePresentation;
        this.jobs = jobs;
    }

    @PostMapping
    public ResponseEntity<QuizDtos.QuizResponse> create(@Valid @RequestBody QuizDtos.SaveRequest request,
                                                        Principal principal) {
        Quiz quiz = service.createManual(actors.requireUserId(principal), request);
        return ResponseEntity.created(URI.create("/api/quizzes/" + quiz.getId()))
                .body(QuizDtos.QuizResponse.forOwner(quiz, 0));
    }

    @GetMapping
    public Page<QuizDtos.QuizResponse> list(@RequestParam(required = false) UUID topicId,
                                           Principal principal, Pageable pageable) {
        UUID actorId = actors.requireUserId(principal);
        Page<Quiz> result = topicId == null ? service.listOwned(actorId, pageable)
                : service.listOwnedByTopic(actorId, topicId, pageable);
        return result
                .map(quiz -> QuizDtos.QuizResponse.forOwner(
                        quiz, service.questionCount(quiz.getId())));
    }

    @GetMapping("/{quizId}")
    public QuizDtos.QuizResponse get(@PathVariable UUID quizId, Principal principal) {
        UUID actorId = actors.requireUserId(principal);
        Quiz quiz = service.getAccessible(actorId, quizId);
        return quiz.getOwnerId().equals(actorId)
                ? QuizDtos.QuizResponse.forOwner(quiz, service.questionCount(quizId))
                : QuizDtos.QuizResponse.from(quiz, service.questionCount(quizId));
    }

    @GetMapping("/{quizId}/sources")
    public List<SourceDtos.Response> sources(@PathVariable UUID quizId, Principal principal) {
        return service.listSources(actors.requireUserId(principal), quizId).stream()
                .map(sourcePresentation::response).toList();
    }

    @GetMapping("/{quizId}/generation/job")
    public JobDtos.Response latestGenerationJob(
            @PathVariable UUID quizId, Principal principal) {
        return JobDtos.Response.from(jobs.latestOwnedQuizGeneration(
                actors.requireUserId(principal), quizId));
    }

    @PutMapping("/{quizId}")
    public QuizDtos.QuizResponse update(@PathVariable UUID quizId,
                                        @Valid @RequestBody QuizDtos.SaveRequest request,
                                        Principal principal) {
        Quiz quiz = service.update(actors.requireUserId(principal), quizId, request);
        return QuizDtos.QuizResponse.forOwner(quiz, service.questionCount(quizId));
    }

    @PostMapping("/{quizId}/publish")
    public QuizDtos.QuizResponse publish(@PathVariable UUID quizId, Principal principal) {
        currentUser.requireVerified();
        Quiz quiz = service.publish(actors.requireUserId(principal), quizId);
        return QuizDtos.QuizResponse.forOwner(quiz, service.questionCount(quizId));
    }

    @PostMapping("/generate")
    public ResponseEntity<QuizDtos.GenerateResponse> generate(
            @Valid @RequestBody QuizDtos.GenerateRequest request,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            Principal principal) {
        currentUser.requireVerified();
        var result = service.generate(actors.requireUserId(principal), request, idempotencyKey);
        var body = new QuizDtos.GenerateResponse(
                QuizDtos.QuizResponse.forOwner(result.quiz(), service.questionCount(result.quiz().getId())),
                result.job().getId());
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .header(HttpHeaders.LOCATION, "/api/jobs/" + result.job().getId()).body(body);
    }

    @PostMapping("/{quizId}/generation/retry")
    public ResponseEntity<QuizDtos.GenerateResponse> retry(
            @PathVariable UUID quizId,
            @Valid @RequestBody QuizDtos.GenerateRequest request,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            Principal principal) {
        currentUser.requireVerified();
        var result = service.retry(actors.requireUserId(principal), quizId, request, idempotencyKey);
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .header(HttpHeaders.LOCATION, "/api/jobs/" + result.job().getId())
                .body(new QuizDtos.GenerateResponse(
                        QuizDtos.QuizResponse.forOwner(result.quiz(), service.questionCount(quizId)), result.job().getId()));
    }

    @PostMapping("/{quizId}/generation/retry-last")
    public ResponseEntity<QuizDtos.GenerateResponse> retryLast(
            @PathVariable UUID quizId,
            Principal principal) {
        currentUser.requireVerified();
        var result = service.retryLast(actors.requireUserId(principal), quizId);
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .header(HttpHeaders.LOCATION, "/api/jobs/" + result.job().getId())
                .body(new QuizDtos.GenerateResponse(
                        QuizDtos.QuizResponse.forOwner(
                                result.quiz(), service.questionCount(quizId)),
                        result.job().getId()));
    }

    @PostMapping("/{quizId}/generation/append")
    public ResponseEntity<QuizDtos.GenerateResponse> appendGeneration(
            @PathVariable UUID quizId,
            @Valid @RequestBody QuizDtos.AppendGenerateRequest request,
            @RequestHeader(
                    value = "Idempotency-Key",
                    required = false) String idempotencyKey,
            Principal principal) {
        currentUser.requireVerified();
        var result = service.appendGeneration(
                actors.requireUserId(principal),
                quizId,
                request,
                idempotencyKey);
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .header(
                        HttpHeaders.LOCATION,
                        "/api/jobs/" + result.job().getId())
                .body(new QuizDtos.GenerateResponse(
                        QuizDtos.QuizResponse.forOwner(
                                result.quiz(),
                                service.questionCount(quizId)),
                        result.job().getId()));
    }

    @GetMapping("/{quizId}/generation/jobs")
    public List<JobDtos.Response> generationJobs(
            @PathVariable UUID quizId,
            @RequestParam(defaultValue = "20") int limit,
            Principal principal) {
        UUID actorId = actors.requireUserId(principal);
        service.getOwned(actorId, quizId);
        return jobs.ownedQuizGenerationHistory(actorId, quizId, limit)
                .stream().map(JobDtos.Response::from).toList();
    }

    @DeleteMapping("/{quizId}")
    public ResponseEntity<Void> delete(@PathVariable UUID quizId, Principal principal) {
        service.delete(actors.requireUserId(principal), quizId);
        return ResponseEntity.noContent().build();
    }
}
