package com.genquiz.bk.quiz;

import com.genquiz.bk.topic.ActorIdentityService;
import jakarta.validation.Valid;
import java.net.URI;
import java.security.Principal;
import java.util.List;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class QuestionController {
    private final QuestionService service;
    private final ActorIdentityService actors;

    public QuestionController(QuestionService service, ActorIdentityService actors) {
        this.service = service;
        this.actors = actors;
    }

    @GetMapping("/quizzes/{quizId}/questions")
    public List<QuizDtos.QuestionResponse> list(@PathVariable UUID quizId, Principal principal) {
        return service.listForOwner(actors.requireUserId(principal), quizId);
    }

    @PostMapping("/quizzes/{quizId}/questions")
    public ResponseEntity<QuizDtos.QuestionResponse> create(@PathVariable UUID quizId,
                                                            @Valid @RequestBody QuizDtos.QuestionRequest request,
                                                            Principal principal) {
        var question = service.create(actors.requireUserId(principal), quizId, request);
        return ResponseEntity.created(URI.create("/api/questions/" + question.id())).body(question);
    }

    @PutMapping("/questions/{questionId}")
    public QuizDtos.QuestionResponse update(@PathVariable UUID questionId,
                                            @Valid @RequestBody QuizDtos.QuestionRequest request,
                                            Principal principal) {
        return service.update(actors.requireUserId(principal), questionId, request);
    }

    @PutMapping("/quizzes/{quizId}/questions/reorder")
    public List<QuizDtos.QuestionResponse> reorder(@PathVariable UUID quizId,
                                                   @Valid @RequestBody QuizDtos.ReorderRequest request,
                                                   Principal principal) {
        return service.reorder(actors.requireUserId(principal), quizId, request.questionIds());
    }

    @DeleteMapping("/questions/{questionId}")
    public ResponseEntity<Void> delete(@PathVariable UUID questionId, Principal principal) {
        service.delete(actors.requireUserId(principal), questionId);
        return ResponseEntity.noContent().build();
    }
}
