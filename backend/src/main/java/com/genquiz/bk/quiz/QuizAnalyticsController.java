package com.genquiz.bk.quiz;

import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.PageMetadata;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/quizzes/{quizId}/analytics")
public class QuizAnalyticsController {
    private final QuizAnalyticsService service;

    public QuizAnalyticsController(QuizAnalyticsService service) { this.service = service; }

    @GetMapping("/summary")
    public ApiEnvelope<QuizAnalyticsDtos.Summary> summary(@PathVariable UUID quizId, Authentication auth) {
        return ApiEnvelope.success("Lấy thống kê quiz thành công.", service.summary(actor(auth), quizId));
    }

    @GetMapping("/participants")
    public ApiEnvelope<List<QuizAnalyticsDtos.Participant>> participants(@PathVariable UUID quizId,
            @RequestParam(defaultValue="1") @Min(1) int page,
            @RequestParam(defaultValue="20") @Min(1) @Max(100) int limit, Authentication auth) {
        Page<QuizAnalyticsDtos.Participant> result = service.participants(actor(auth), quizId, page, limit);
        return ApiEnvelope.page("Lấy danh sách người làm thành công.", result.getContent(),
                new PageMetadata(page, limit, result.getTotalElements(), result.getTotalPages(),
                        result.hasNext(), result.hasPrevious()));
    }

    @GetMapping("/questions")
    public ApiEnvelope<List<QuizAnalyticsDtos.Question>> questions(@PathVariable UUID quizId, Authentication auth) {
        return ApiEnvelope.success("Lấy thống kê câu hỏi thành công.", service.questions(actor(auth), quizId));
    }

    private UUID actor(Authentication auth) { return UUID.fromString(auth.getName()); }
}
