package com.genquiz.bk.quiz;

import com.genquiz.bk.topic.ActorIdentityService;
import jakarta.validation.Valid;
import java.net.URI;
import java.security.Principal;
import java.util.List;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.multipart.MultipartFile;
import com.genquiz.bk.security.CurrentUser;
import com.genquiz.bk.user.Role;

@RestController
@RequestMapping("/api")
public class QuestionController {
    private final QuestionService service;
    private final ActorIdentityService actors;
    private final CurrentUser currentUser;
    private final QuestionExcelImportService excelImport;

    public QuestionController(QuestionService service, ActorIdentityService actors,
                              CurrentUser currentUser, QuestionExcelImportService excelImport) {
        this.service = service;
        this.actors = actors;
        this.currentUser = currentUser;
        this.excelImport = excelImport;
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

    @GetMapping("/questions/import-template")
    public ResponseEntity<byte[]> importTemplate() {
        byte[] content = excelImport.template();
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .contentLength(content.length)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=BKQuiz-Mau-Import-Cau-Hoi.xlsx")
                .body(content);
    }

    @PostMapping(value = "/quizzes/{quizId}/questions/import",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public QuizDtos.QuestionImportResponse importQuestions(
            @PathVariable UUID quizId, @RequestPart("file") MultipartFile file,
            Principal principal) {
        return excelImport.importFile(actors.requireUserId(principal), quizId, file);
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

    @PutMapping("/questions/{questionId}/validation-review")
    public QuizDtos.QuestionResponse reviewValidation(
            @PathVariable UUID questionId,
            @Valid @RequestBody QuizDtos.ValidationReviewRequest request,
            Principal principal) {
        currentUser.requireVerified();
        var user = currentUser.require();
        return service.reviewValidation(actors.requireUserId(principal),
                user.getRole() == Role.ADMIN, questionId, request.note());
    }

    @DeleteMapping("/questions/{questionId}/validation-review")
    public QuizDtos.QuestionResponse undoValidationReview(
            @PathVariable UUID questionId, Principal principal) {
        currentUser.requireVerified();
        var user = currentUser.require();
        return service.undoValidationReview(actors.requireUserId(principal),
                user.getRole() == Role.ADMIN, questionId);
    }
}
