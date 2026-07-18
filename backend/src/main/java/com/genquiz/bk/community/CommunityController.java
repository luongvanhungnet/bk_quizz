package com.genquiz.bk.community;

import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.PageMetadata;
import com.genquiz.bk.common.error.ApiException;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@Validated
@RestController
@RequestMapping("/api")
public class CommunityController {
    private final CommunityService service;

    public CommunityController(CommunityService service) { this.service = service; }

    @PutMapping("/quizzes/{quizId}/bookmark")
    public ApiEnvelope<CommunityDtos.BookmarkResponse> bookmark(@PathVariable UUID quizId,
                                                                 Authentication authentication) {
        return ApiEnvelope.success("Đã lưu bài kiểm tra.", service.bookmark(actor(authentication), quizId));
    }

    @DeleteMapping("/quizzes/{quizId}/bookmark")
    public ResponseEntity<Void> unbookmark(@PathVariable UUID quizId, Authentication authentication) {
        service.unbookmark(actor(authentication), quizId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/bookmarks")
    public ApiEnvelope<List<CommunityDtos.BookmarkResponse>> bookmarks(
            @RequestParam(defaultValue = "1") @Min(1) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
            Authentication authentication) {
        Page<CommunityDtos.BookmarkResponse> result = service.bookmarks(actor(authentication), page, limit);
        return ApiEnvelope.page("Lấy danh sách bài kiểm tra đã lưu thành công.", result.getContent(),
                metadata(result, page, limit));
    }

    @PutMapping("/quizzes/{quizId}/rating")
    public ApiEnvelope<CommunityDtos.RatingResponse> rate(@PathVariable UUID quizId,
                                                          @Valid @RequestBody CommunityDtos.RatingRequest request,
                                                          Authentication authentication) {
        return ApiEnvelope.success("Đánh giá bài kiểm tra thành công.",
                service.rate(actor(authentication), quizId, request));
    }

    @DeleteMapping("/quizzes/{quizId}/rating")
    public ResponseEntity<Void> deleteRating(@PathVariable UUID quizId, Authentication authentication) {
        service.deleteRating(actor(authentication), quizId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/quizzes/{quizId}/ratings")
    public ApiEnvelope<List<CommunityDtos.RatingResponse>> ratings(
            @PathVariable UUID quizId,
            @RequestParam(defaultValue = "1") @Min(1) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
            Authentication authentication) {
        Page<CommunityDtos.RatingResponse> result = service.ratings(actor(authentication), quizId, page, limit);
        return ApiEnvelope.page("Lấy danh sách đánh giá thành công.", result.getContent(),
                metadata(result, page, limit));
    }

    @GetMapping("/quizzes/{quizId}/community-stats")
    public ApiEnvelope<CommunityDtos.StatisticsResponse> statistics(@PathVariable UUID quizId,
                                                                    Authentication authentication) {
        return ApiEnvelope.success("Lấy thống kê cộng đồng thành công.",
                service.statistics(actor(authentication), quizId));
    }

    private static UUID actor(Authentication authentication) {
        if (authentication == null || authentication.getName() == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "Bạn cần đăng nhập.");
        }
        try {
            return UUID.fromString(authentication.getName());
        } catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_AUTHENTICATION", "Phiên đăng nhập không hợp lệ.");
        }
    }

    private static PageMetadata metadata(Page<?> result, int page, int limit) {
        return new PageMetadata(page, limit, result.getTotalElements(), result.getTotalPages(),
                result.hasNext(), result.hasPrevious());
    }
}
