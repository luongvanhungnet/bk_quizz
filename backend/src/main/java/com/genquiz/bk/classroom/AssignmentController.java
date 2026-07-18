package com.genquiz.bk.classroom;

import com.genquiz.bk.common.api.ApiEnvelope;
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
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.List;
import java.util.UUID;

@Validated
@RestController
@RequestMapping("/api")
public class AssignmentController {
    private final AssignmentService service;

    public AssignmentController(AssignmentService service) { this.service = service; }

    @PostMapping("/classrooms/{classroomId}/assignments")
    public ResponseEntity<ApiEnvelope<ClassroomDtos.AssignmentResponse>> create(
            @PathVariable UUID classroomId, @Valid @RequestBody ClassroomDtos.AssignmentRequest request,
            Authentication authentication) {
        ClassroomDtos.AssignmentResponse response = service.create(
                ClassroomController.actor(authentication), classroomId, request);
        return ResponseEntity.created(URI.create("/api/assignments/" + response.id()))
                .body(ApiEnvelope.success("Tạo bài tập thành công.", response));
    }

    @GetMapping("/classrooms/{classroomId}/assignments")
    public ApiEnvelope<List<ClassroomDtos.AssignmentResponse>> list(
            @PathVariable UUID classroomId,
            @RequestParam(defaultValue = "1") @Min(1) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
            Authentication authentication) {
        Page<ClassroomDtos.AssignmentResponse> result = service.list(
                ClassroomController.actor(authentication), classroomId, page, limit);
        return ApiEnvelope.page("Lấy danh sách bài tập thành công.", result.getContent(),
                ClassroomController.metadata(result, page, limit));
    }

    @GetMapping("/assignments/{assignmentId}")
    public ApiEnvelope<ClassroomDtos.AssignmentResponse> get(@PathVariable UUID assignmentId,
                                                              Authentication authentication) {
        return ApiEnvelope.success("Lấy bài tập thành công.",
                service.get(ClassroomController.actor(authentication), assignmentId));
    }

    @PatchMapping("/assignments/{assignmentId}")
    public ApiEnvelope<ClassroomDtos.AssignmentResponse> update(
            @PathVariable UUID assignmentId,
            @Valid @RequestBody ClassroomDtos.AssignmentUpdateRequest request,
            Authentication authentication) {
        return ApiEnvelope.success("Cập nhật bài tập thành công.",
                service.update(ClassroomController.actor(authentication), assignmentId, request));
    }

    @PostMapping("/assignments/{assignmentId}/publish")
    public ApiEnvelope<ClassroomDtos.AssignmentResponse> publish(@PathVariable UUID assignmentId,
                                                                  Authentication authentication) {
        return ApiEnvelope.success("Giao bài tập thành công.",
                service.publish(ClassroomController.actor(authentication), assignmentId));
    }

    @PostMapping("/assignments/{assignmentId}/close")
    public ApiEnvelope<ClassroomDtos.AssignmentResponse> close(@PathVariable UUID assignmentId,
                                                                Authentication authentication) {
        return ApiEnvelope.success("Đóng bài tập thành công.",
                service.close(ClassroomController.actor(authentication), assignmentId));
    }

    @DeleteMapping("/assignments/{assignmentId}")
    public ResponseEntity<Void> delete(@PathVariable UUID assignmentId, Authentication authentication) {
        service.delete(ClassroomController.actor(authentication), assignmentId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/assignments/{assignmentId}/submissions")
    public ApiEnvelope<List<ClassroomDtos.SubmissionResponse>> submissions(
            @PathVariable UUID assignmentId,
            @RequestParam(defaultValue = "1") @Min(1) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
            Authentication authentication) {
        Page<ClassroomDtos.SubmissionResponse> result = service.submissions(
                ClassroomController.actor(authentication), assignmentId, page, limit);
        return ApiEnvelope.page("Lấy danh sách bài nộp thành công.", result.getContent(),
                ClassroomController.metadata(result, page, limit));
    }
}
