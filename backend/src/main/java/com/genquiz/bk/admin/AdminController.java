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
import org.springframework.security.access.prepost.PreAuthorize;
import com.genquiz.bk.abuse.AccountReputationService;
import com.genquiz.bk.abuse.RiskAssessment;

@Validated
@RestController
@RequestMapping("/api/admin")
public class AdminController {
    private final AdminService service;
    private final AdminRoleService roleService;
    private final AccountReputationService reputationService;
    public AdminController(AdminService service, AdminRoleService roleService,
                           AccountReputationService reputationService) {
        this.service=service; this.roleService=roleService; this.reputationService=reputationService;
    }

    @PreAuthorize("hasAuthority('analytics:read')")
    @GetMapping("/summary") ApiEnvelope<AdminDtos.Summary> summary() { return ApiEnvelope.success("Lấy tổng quan quản trị thành công.",service.summary()); }
    @PreAuthorize("hasAuthority('user:read')")
    @GetMapping("/users") ApiEnvelope<List<UserDto>> users(@RequestParam(defaultValue="") String search,@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){Page<UserDto> result=service.users(search,page,limit);return ApiEnvelope.page("Lấy danh sách tài khoản thành công.",result.getContent(),metadata(result,page,limit));}
    @PreAuthorize("hasAuthority('user:read')")
    @GetMapping("/users/{id}") ApiEnvelope<UserDto> user(@PathVariable UUID id){return ApiEnvelope.success("Lấy tài khoản thành công.",service.user(id));}
    @PreAuthorize("hasAuthority('user:read') and hasAuthority('risk:read')")
    @GetMapping("/users/{id}/investigation") ApiEnvelope<AdminDtos.UserInvestigation> investigation(@PathVariable UUID id){return ApiEnvelope.success("Lấy hồ sơ điều tra tài khoản thành công.",service.investigation(id));}
    @PreAuthorize("hasAuthority('quota:update')")
    @PatchMapping("/users/{id}/quota") ApiEnvelope<Void> quota(@PathVariable UUID id,@Valid @RequestBody AdminDtos.QuotaAdjustment request){service.adjustQuota(id,request);return ApiEnvelope.success("Đã cập nhật hạn mức.",null);}
    @PreAuthorize("hasAuthority('user:ban')")
    @PostMapping("/users/{id}/ban") ApiEnvelope<UserDto> ban(@PathVariable UUID id){return ApiEnvelope.success("Đã cấm tài khoản.",service.ban(id));}
    @PreAuthorize("hasAuthority('user:ban')")
    @PostMapping("/users/{id}/restore") ApiEnvelope<UserDto> restore(@PathVariable UUID id){return ApiEnvelope.success("Đã khôi phục tài khoản.",service.restore(id));}
    @PreAuthorize("hasAuthority('admin:grant')")
    @PatchMapping("/users/{id}/role") ApiEnvelope<UserDto> role(@PathVariable UUID id,@Valid @RequestBody AdminDtos.ChangeRoleRequest request){Role role=request.role()==AdminDtos.ManagedRole.TEACHER?Role.TEACHER:Role.STUDENT;return ApiEnvelope.success("Cập nhật vai trò thành công.",service.changeRole(id,role));}
    @PreAuthorize("hasAuthority('user:suspend')")
    @PatchMapping("/users/{id}/status") ApiEnvelope<UserDto> status(@PathVariable UUID id,@Valid @RequestBody AdminDtos.ChangeStatusRequest request){return ApiEnvelope.success("Cập nhật trạng thái thành công.",service.changeStatus(id,request.active()));}
    @PreAuthorize("hasAuthority('user:suspend')")
    @PostMapping("/users/{id}/revoke-sessions") ApiEnvelope<Void> revoke(@PathVariable UUID id){service.revokeSessions(id);return ApiEnvelope.success("Đã thu hồi mọi phiên.",null);}

    @PreAuthorize("hasAuthority('admin:read')")
    @GetMapping("/users/{id}/roles")
    ApiEnvelope<AdminDtos.UserRoles> roles(@PathVariable UUID id) {
        return ApiEnvelope.success("Lấy vai trò quản trị thành công.",
                new AdminDtos.UserRoles(id, roleService.roles(id)));
    }

    @PreAuthorize("hasAuthority('admin:grant')")
    @PostMapping("/users/{id}/roles/{role}")
    ApiEnvelope<AdminDtos.UserRoles> grantRole(@PathVariable UUID id, @PathVariable String role) {
        return ApiEnvelope.success("Đã cấp vai trò quản trị.",
                new AdminDtos.UserRoles(id, roleService.grant(id, role)));
    }

    @PreAuthorize("hasAuthority('admin:revoke')")
    @DeleteMapping("/users/{id}/roles/{role}")
    ApiEnvelope<AdminDtos.UserRoles> revokeRole(@PathVariable UUID id, @PathVariable String role) {
        return ApiEnvelope.success("Đã thu hồi vai trò quản trị.",
                new AdminDtos.UserRoles(id, roleService.revoke(id, role)));
    }

    @PreAuthorize("hasAuthority('risk:read')")
    @GetMapping("/users/{id}/risk")
    ApiEnvelope<RiskAssessment> risk(@PathVariable UUID id) {
        return ApiEnvelope.success("Lấy đánh giá rủi ro tài khoản thành công.", reputationService.assess(id));
    }

    @PreAuthorize("hasAuthority('admin:read')")
    @GetMapping("/files") ApiEnvelope<List<FileDto>> files(@RequestParam(defaultValue="") String search,@RequestParam(required=false) StoredFile.Status status,@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){Page<StoredFile> result=service.files(search,status,page,limit);return ApiEnvelope.page("Lấy danh sách file thành công.",result.map(FileDto::from).getContent(),metadata(result,page,limit));}
    @PreAuthorize("hasAuthority('system:config')")
    @PatchMapping("/files/{id}/status") ApiEnvelope<FileDto> fileStatus(@PathVariable UUID id,@RequestBody FileStatusRequest request){return ApiEnvelope.success("Cập nhật file thành công.",FileDto.from(service.fileStatus(id,request.status())));}
    @PreAuthorize("hasAuthority('admin:read')")
    @GetMapping("/jobs") ApiEnvelope<List<JobDto>> jobs(@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){Page<Job> result=service.jobs(page,limit);return ApiEnvelope.page("Lấy danh sách job thành công.",result.map(JobDto::from).getContent(),metadata(result,page,limit));}
    @PreAuthorize("hasAuthority('system:config')")
    @PostMapping("/jobs/{id}/retry") ApiEnvelope<JobDto> retry(@PathVariable UUID id){return ApiEnvelope.success("Đã đưa job vào hàng đợi.",JobDto.from(service.retryJob(id)));}
    @PreAuthorize("hasAuthority('system:config')")
    @PostMapping("/jobs/{id}/cancel") ApiEnvelope<JobDto> cancel(@PathVariable UUID id){return ApiEnvelope.success("Đã hủy job.",JobDto.from(service.cancelJob(id)));}
    @PreAuthorize("hasAuthority('admin:read')")
    @GetMapping("/content/{type}") ApiEnvelope<List<Map<String,Object>>> content(@PathVariable String type){return ApiEnvelope.success("Lấy nội dung thành công.",service.content(type));}
    @PreAuthorize("hasAuthority('risk:update')")
    @PatchMapping("/content/{type}/{id}/moderation") ApiEnvelope<Void> moderate(@PathVariable String type,@PathVariable UUID id,@RequestBody ModerationRequest request){service.moderate(type,id,request.hidden(),request.reason());return ApiEnvelope.success("Đã cập nhật kiểm duyệt.",null);}
    @PreAuthorize("hasAuthority('audit:read')")
    @GetMapping("/audit-logs") ApiEnvelope<List<AdminDtos.AuditDto>> audit(@RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){Page<AdminDtos.AuditDto> result=service.audit(page,limit);return ApiEnvelope.page("Lấy nhật ký quản trị thành công.",result.getContent(),metadata(result,page,limit));}
    @PreAuthorize("hasAuthority('audit:read')")
    @GetMapping("/audit-events") ApiEnvelope<List<AdminDtos.AuditDto>> auditEvents(
            @RequestParam(required=false) Instant dateFrom,@RequestParam(required=false) Instant dateTo,
            @RequestParam(required=false) String eventType,@RequestParam(required=false) UUID actorId,
            @RequestParam(required=false) String targetType,@RequestParam(required=false) String targetId,
            @RequestParam(defaultValue="1") @Min(1) int page,@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit){
        Page<AdminDtos.AuditDto> result=service.audit(dateFrom,dateTo,eventType,actorId,targetType,targetId,page,limit);
        return ApiEnvelope.page("Lấy nhật ký kiểm toán thành công.",result.getContent(),metadata(result,page,limit));}

    private PageMetadata metadata(Page<?> value,int page,int limit){return new PageMetadata(page,limit,value.getTotalElements(),value.getTotalPages(),value.hasNext(),value.hasPrevious());}
    record FileStatusRequest(StoredFile.Status status){}
    record ModerationRequest(boolean hidden,String reason){}
    record JobDto(UUID id,String type,String status,UUID subjectUserId,UUID resourceId,int attempts,int maxAttempts,String errorCode,String errorMessage,Instant createdAt){static JobDto from(Job j){return new JobDto(j.getId(),j.getType().name(),j.getStatus().name(),j.getSubjectUserId(),j.getResourceId(),j.getAttempts(),j.getMaxAttempts(),j.getErrorCode(),j.getErrorMessage(),j.getCreatedAt());}}
    record FileDto(UUID id,UUID ownerId,String purpose,String provider,String originalName,String mediaType,long sizeBytes,String sha256,String status,Instant createdAt){static FileDto from(StoredFile f){return new FileDto(f.getId(),f.getOwnerId(),f.getPurpose().name(),f.getProvider().name(),f.getOriginalName(),f.getDetectedMediaType(),f.getSizeBytes(),f.getSha256(),f.getStatus().name(),f.getCreatedAt());}}
}
