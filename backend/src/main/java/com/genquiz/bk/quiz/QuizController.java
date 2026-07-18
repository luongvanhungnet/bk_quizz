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

@RestController
@RequestMapping("/api/quizzes")
public class QuizController {
    private final QuizService service;
    private final ActorIdentityService actors;
    private final CurrentUser currentUser;

    public QuizController(QuizService service, ActorIdentityService actors, CurrentUser currentUser) {
        this.service = service;
        this.actors = actors;
        this.currentUser = currentUser;
    }

    @PostMapping
    public ResponseEntity<QuizDtos.QuizResponse> create(@Valid @RequestBody QuizDtos.SaveRequest request,
                                                        Principal principal) {
        Quiz quiz = service.createManual(actors.requireUserId(principal), request);
        return ResponseEntity.created(URI.create("/api/quizzes/" + quiz.getId()))
                .body(QuizDtos.QuizResponse.from(quiz, 0));
    }

    @GetMapping
    public Page<QuizDtos.QuizResponse> list(@RequestParam(required = false) UUID topicId,
                                           Principal principal, Pageable pageable) {
        UUID actorId = actors.requireUserId(principal);
        Page<Quiz> result = topicId == null ? service.listOwned(actorId, pageable)
                : service.listOwnedByTopic(actorId, topicId, pageable);
        return result
                .map(quiz -> QuizDtos.QuizResponse.from(quiz, service.questionCount(quiz.getId())));
    }

    @GetMapping("/{quizId}")
    public QuizDtos.QuizResponse get(@PathVariable UUID quizId, Principal principal) {
        Quiz quiz = service.getAccessible(actors.requireUserId(principal), quizId);
        return QuizDtos.QuizResponse.from(quiz, service.questionCount(quizId));
    }

    @PutMapping("/{quizId}")
    public QuizDtos.QuizResponse update(@PathVariable UUID quizId,
                                        @Valid @RequestBody QuizDtos.SaveRequest request,
                                        Principal principal) {
        Quiz quiz = service.update(actors.requireUserId(principal), quizId, request);
        return QuizDtos.QuizResponse.from(quiz, service.questionCount(quizId));
    }

    @PostMapping("/{quizId}/publish")
    public QuizDtos.QuizResponse publish(@PathVariable UUID quizId, Principal principal) {
        currentUser.requireVerified();
        Quiz quiz = service.publish(actors.requireUserId(principal), quizId);
        return QuizDtos.QuizResponse.from(quiz, service.questionCount(quizId));
    }

    @PostMapping("/generate")
    public ResponseEntity<QuizDtos.GenerateResponse> generate(
            @Valid @RequestBody QuizDtos.GenerateRequest request,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            Principal principal) {
        currentUser.requireVerified();
        var result = service.generate(actors.requireUserId(principal), request, idempotencyKey);
        var body = new QuizDtos.GenerateResponse(
                QuizDtos.QuizResponse.from(result.quiz(), service.questionCount(result.quiz().getId())),
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
                        QuizDtos.QuizResponse.from(result.quiz(), service.questionCount(quizId)), result.job().getId()));
    }

    @DeleteMapping("/{quizId}")
    public ResponseEntity<Void> delete(@PathVariable UUID quizId, Principal principal) {
        service.delete(actors.requireUserId(principal), quizId);
        return ResponseEntity.noContent().build();
    }
}
