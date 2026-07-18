package com.genquiz.bk.classroom;

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
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.PutMapping;

import java.net.URI;
import java.util.List;
import java.util.UUID;

@Validated
@RestController
@RequestMapping("/api/classrooms")
public class ClassroomController {
    private final ClassroomService service;

    public ClassroomController(ClassroomService service) { this.service = service; }

    @PostMapping
    public ResponseEntity<ApiEnvelope<ClassroomDtos.ClassroomResponse>> create(
            @Valid @RequestBody ClassroomDtos.SaveRequest request, Authentication authentication) {
        ClassroomDtos.ClassroomResponse response = service.create(actor(authentication), request);
        return ResponseEntity.created(URI.create("/api/classrooms/" + response.id()))
                .body(ApiEnvelope.success("Tạo lớp học thành công.", response));
    }

    @GetMapping
    public ApiEnvelope<List<ClassroomDtos.ClassroomResponse>> list(
            @RequestParam(defaultValue = "1") @Min(1) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
            Authentication authentication) {
        Page<ClassroomDtos.ClassroomResponse> result = service.list(actor(authentication), page, limit);
        return ApiEnvelope.page("Lấy danh sách lớp học thành công.", result.getContent(), metadata(result, page, limit));
    }

    @GetMapping("/{classroomId}")
    public ApiEnvelope<ClassroomDtos.ClassroomResponse> get(@PathVariable UUID classroomId,
                                                             Authentication authentication) {
        return ApiEnvelope.success("Lấy thông tin lớp học thành công.", service.get(actor(authentication), classroomId));
    }

    @PatchMapping("/{classroomId}")
    public ApiEnvelope<ClassroomDtos.ClassroomResponse> update(@PathVariable UUID classroomId,
                                                                @Valid @RequestBody ClassroomDtos.SaveRequest request,
                                                                Authentication authentication) {
        return ApiEnvelope.success("Cập nhật lớp học thành công.",
                service.update(actor(authentication), classroomId, request));
    }

    @PostMapping("/join")
    public ApiEnvelope<ClassroomDtos.ClassroomResponse> join(@Valid @RequestBody ClassroomDtos.JoinRequest request,
                                                              Authentication authentication) {
        return ApiEnvelope.success("Tham gia lớp học thành công.",
                service.join(actor(authentication), request.joinCode()));
    }

    @GetMapping("/join/{joinCode}/preview")
    public ApiEnvelope<ClassroomDtos.JoinPreview> preview(@PathVariable String joinCode) {
        return ApiEnvelope.success("Lấy thông tin lớp học thành công.", service.preview(joinCode));
    }

    @PostMapping("/{classroomId}/join-code/rotate")
    public ApiEnvelope<ClassroomDtos.ClassroomResponse> rotate(@PathVariable UUID classroomId, Authentication auth) {
        return ApiEnvelope.success("Đã đổi mã tham gia.", service.rotateJoinCode(actor(auth), classroomId));
    }

    @PatchMapping("/{classroomId}/join-settings")
    public ApiEnvelope<ClassroomDtos.ClassroomResponse> joinSettings(@PathVariable UUID classroomId,
            @RequestBody ClassroomDtos.JoinSettingsRequest request, Authentication auth) {
        return ApiEnvelope.success("Đã cập nhật cài đặt tham gia.",
                service.updateJoinSettings(actor(auth), classroomId, request.enabled()));
    }

    @GetMapping("/{classroomId}/members")
    public ApiEnvelope<List<ClassroomDtos.MemberResponse>> members(@PathVariable UUID classroomId,
                                                                   Authentication authentication) {
        return ApiEnvelope.success("Lấy danh sách thành viên thành công.",
                service.listMembers(actor(authentication), classroomId));
    }

    @PostMapping("/{classroomId}/members")
    public ResponseEntity<ApiEnvelope<ClassroomDtos.MemberResponse>> addMember(
            @PathVariable UUID classroomId, @Valid @RequestBody ClassroomDtos.AddMemberRequest request,
            Authentication authentication) {
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiEnvelope.success("Thêm thành viên thành công.",
                service.addMember(actor(authentication), classroomId, request)));
    }

    @DeleteMapping("/{classroomId}/members/{userId}")
    public ResponseEntity<Void> removeMember(@PathVariable UUID classroomId, @PathVariable UUID userId,
                                              Authentication authentication) {
        service.removeMember(actor(authentication), classroomId, userId);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{classroomId}/leave")
    public ResponseEntity<Void> leave(@PathVariable UUID classroomId, Authentication authentication) {
        service.leave(actor(authentication), classroomId);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{classroomId}/archive")
    public ApiEnvelope<ClassroomDtos.ClassroomResponse> archive(@PathVariable UUID classroomId,
                                                                 Authentication authentication) {
        return ApiEnvelope.success("Lưu trữ lớp học thành công.", service.archive(actor(authentication), classroomId));
    }

    static UUID actor(Authentication authentication) {
        if (authentication == null || authentication.getName() == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "Bạn cần đăng nhập.");
        }
        try {
            return UUID.fromString(authentication.getName());
        } catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_AUTHENTICATION", "Phiên đăng nhập không hợp lệ.");
        }
    }

    static PageMetadata metadata(Page<?> result, int page, int limit) {
        return new PageMetadata(page, limit, result.getTotalElements(), result.getTotalPages(),
                result.hasNext(), result.hasPrevious());
    }
}
