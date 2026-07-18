package com.genquiz.bk.admin;

import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.PageMetadata;
import com.genquiz.bk.storage.StoredFile;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.dto.UserDto;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.data.domain.Page;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.Map;
import com.genquiz.bk.job.Job;

@Validated
@RestController
@RequestMapping("/api/admin")
public class AdminController {
    private final AdminService service;
    public AdminController(AdminService service) { this.service=service; }

    @GetMapping("/summary") ApiEnvelope<AdminDtos.Summary> summary() { return ApiEnvelope.success("Lấy tổng quan quản trị thành công.",service.summary()); }
    @GetMapping("/users") ApiEnvelope<List<UserDto>> users(@RequestParam(defaultValue="") String search,@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){Page<UserDto> result=service.users(search,page,limit);return ApiEnvelope.page("Lấy danh sách tài khoản thành công.",result.getContent(),metadata(result,page,limit));}
    @GetMapping("/users/{id}") ApiEnvelope<UserDto> user(@PathVariable UUID id){return ApiEnvelope.success("Lấy tài khoản thành công.",service.user(id));}
    @PatchMapping("/users/{id}/role") ApiEnvelope<UserDto> role(@PathVariable UUID id,@Valid @RequestBody AdminDtos.ChangeRoleRequest request){Role role=request.role()==AdminDtos.ManagedRole.TEACHER?Role.TEACHER:Role.STUDENT;return ApiEnvelope.success("Cập nhật vai trò thành công.",service.changeRole(id,role));}
    @PatchMapping("/users/{id}/status") ApiEnvelope<UserDto> status(@PathVariable UUID id,@Valid @RequestBody AdminDtos.ChangeStatusRequest request){return ApiEnvelope.success("Cập nhật trạng thái thành công.",service.changeStatus(id,request.active()));}
    @PostMapping("/users/{id}/revoke-sessions") ApiEnvelope<Void> revoke(@PathVariable UUID id){service.revokeSessions(id);return ApiEnvelope.success("Đã thu hồi mọi phiên.",null);}

    @GetMapping("/files") ApiEnvelope<List<FileDto>> files(@RequestParam(defaultValue="") String search,@RequestParam(required=false) StoredFile.Status status,@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){Page<StoredFile> result=service.files(search,status,page,limit);return ApiEnvelope.page("Lấy danh sách file thành công.",result.map(FileDto::from).getContent(),metadata(result,page,limit));}
    @PatchMapping("/files/{id}/status") ApiEnvelope<FileDto> fileStatus(@PathVariable UUID id,@RequestBody FileStatusRequest request){return ApiEnvelope.success("Cập nhật file thành công.",FileDto.from(service.fileStatus(id,request.status())));}
    @GetMapping("/jobs") ApiEnvelope<List<JobDto>> jobs(@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){Page<Job> result=service.jobs(page,limit);return ApiEnvelope.page("Lấy danh sách job thành công.",result.map(JobDto::from).getContent(),metadata(result,page,limit));}
    @PostMapping("/jobs/{id}/retry") ApiEnvelope<JobDto> retry(@PathVariable UUID id){return ApiEnvelope.success("Đã đưa job vào hàng đợi.",JobDto.from(service.retryJob(id)));}
    @PostMapping("/jobs/{id}/cancel") ApiEnvelope<JobDto> cancel(@PathVariable UUID id){return ApiEnvelope.success("Đã hủy job.",JobDto.from(service.cancelJob(id)));}
    @GetMapping("/content/{type}") ApiEnvelope<List<Map<String,Object>>> content(@PathVariable String type){return ApiEnvelope.success("Lấy nội dung thành công.",service.content(type));}
    @PatchMapping("/content/{type}/{id}/moderation") ApiEnvelope<Void> moderate(@PathVariable String type,@PathVariable UUID id,@RequestBody ModerationRequest request){service.moderate(type,id,request.hidden(),request.reason());return ApiEnvelope.success("Đã cập nhật kiểm duyệt.",null);}
    @GetMapping("/audit-logs") ApiEnvelope<List<AdminDtos.AuditDto>> audit(@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){Page<AdminDtos.AuditDto> result=service.audit(page,limit);return ApiEnvelope.page("Lấy nhật ký quản trị thành công.",result.getContent(),metadata(result,page,limit));}

    private PageMetadata metadata(Page<?> value,int page,int limit){return new PageMetadata(page,limit,value.getTotalElements(),value.getTotalPages(),value.hasNext(),value.hasPrevious());}
    record FileStatusRequest(StoredFile.Status status){}
    record ModerationRequest(boolean hidden,String reason){}
    record JobDto(UUID id,String type,String status,UUID subjectUserId,UUID resourceId,int attempts,int maxAttempts,String errorCode,String errorMessage,Instant createdAt){static JobDto from(Job j){return new JobDto(j.getId(),j.getType().name(),j.getStatus().name(),j.getSubjectUserId(),j.getResourceId(),j.getAttempts(),j.getMaxAttempts(),j.getErrorCode(),j.getErrorMessage(),j.getCreatedAt());}}
    record FileDto(UUID id,UUID ownerId,String purpose,String provider,String originalName,String mediaType,long sizeBytes,String sha256,String status,Instant createdAt){static FileDto from(StoredFile f){return new FileDto(f.getId(),f.getOwnerId(),f.getPurpose().name(),f.getProvider().name(),f.getOriginalName(),f.getDetectedMediaType(),f.getSizeBytes(),f.getSha256(),f.getStatus().name(),f.getCreatedAt());}}
}
