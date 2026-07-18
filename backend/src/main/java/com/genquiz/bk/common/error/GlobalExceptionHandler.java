package com.genquiz.bk.common.error;

import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.ApiFieldError;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.validation.FieldError;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;

import java.util.List;

@RestControllerAdvice
public class GlobalExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    ResponseEntity<ApiEnvelope<Void>> handleApi(ApiException exception, HttpServletRequest request) {
        return response(exception.status(), exception.getMessage(), exception.errors(), request);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiEnvelope<Void>> handleBodyValidation(MethodArgumentNotValidException exception,
                                                            HttpServletRequest request) {
        List<ApiFieldError> errors = exception.getBindingResult().getAllErrors().stream()
                .map(error -> new ApiFieldError(
                        "VALIDATION_ERROR",
                        error instanceof FieldError field ? field.getField() : null,
                        error.getDefaultMessage() == null ? "Dữ liệu không hợp lệ." : error.getDefaultMessage()))
                .toList();
        return response(HttpStatus.BAD_REQUEST, "Dữ liệu không hợp lệ.", errors, request);
    }

    @ExceptionHandler({ConstraintViolationException.class, HandlerMethodValidationException.class,
            HttpMessageNotReadableException.class, MissingServletRequestParameterException.class})
    ResponseEntity<ApiEnvelope<Void>> handleBadRequest(Exception exception, HttpServletRequest request) {
        return response(HttpStatus.BAD_REQUEST, "Dữ liệu không hợp lệ.",
                List.of(new ApiFieldError("INVALID_REQUEST", "Dữ liệu gửi lên không hợp lệ.")), request);
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<ApiEnvelope<Void>> handleDenied(AccessDeniedException exception, HttpServletRequest request) {
        return response(HttpStatus.FORBIDDEN, "Bạn không có quyền thực hiện thao tác này.",
                List.of(new ApiFieldError("ACCESS_DENIED", "Bạn không có quyền thực hiện thao tác này.")), request);
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ApiEnvelope<Void>> handleConflict(DataIntegrityViolationException exception,
                                                      HttpServletRequest request) {
        return response(HttpStatus.CONFLICT, "Dữ liệu đã tồn tại hoặc đang được sử dụng.",
                List.of(new ApiFieldError("DATA_CONFLICT", "Dữ liệu đã tồn tại hoặc đang được sử dụng.")), request);
    }

    @ExceptionHandler(DataAccessException.class)
    ResponseEntity<ApiEnvelope<Void>> handleDataAccess(DataAccessException exception,
                                                        HttpServletRequest request) {
        log.error("Lỗi truy cập dữ liệu tại {} {} traceId={}", request.getMethod(), request.getRequestURI(),
                request.getAttribute("traceId"), exception);
        if ("/api/classrooms/join".equals(request.getRequestURI())) {
            String message = "Không thể hoàn tất việc tham gia lớp học do lỗi dữ liệu. "
                    + "Vui lòng thử lại; nếu lỗi tiếp diễn, hãy gửi mã yêu cầu cho quản trị viên.";
            return response(HttpStatus.SERVICE_UNAVAILABLE, message,
                    List.of(new ApiFieldError("CLASSROOM_JOIN_DATABASE_ERROR", message)), request);
        }
        String message = "Không thể truy cập dữ liệu lúc này. Vui lòng thử lại và cung cấp mã yêu cầu nếu lỗi tiếp diễn.";
        return response(HttpStatus.SERVICE_UNAVAILABLE, message,
                List.of(new ApiFieldError("DATABASE_UNAVAILABLE", message)), request);
    }

    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<ApiEnvelope<Void>> handleStatus(ResponseStatusException exception, HttpServletRequest request) {
        HttpStatus status = HttpStatus.resolve(exception.getStatusCode().value());
        if (status == null) status = HttpStatus.INTERNAL_SERVER_ERROR;
        String message = exception.getReason() == null ? "Yêu cầu không thể được xử lý." : exception.getReason();
        return response(status, message,
                List.of(new ApiFieldError("REQUEST_REJECTED", message)), request);
    }

    @ExceptionHandler(ObjectOptimisticLockingFailureException.class)
    ResponseEntity<ApiEnvelope<Void>> handleOptimisticLock(ObjectOptimisticLockingFailureException exception,
                                                            HttpServletRequest request) {
        return response(HttpStatus.CONFLICT, "Dữ liệu đã được thay đổi ở một phiên khác.",
                List.of(new ApiFieldError("CONCURRENT_MODIFICATION",
                        "Hãy tải lại dữ liệu trước khi thử lại.")), request);
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ApiEnvelope<Void>> handleUploadSize(MaxUploadSizeExceededException exception,
                                                       HttpServletRequest request) {
        return response(HttpStatus.CONTENT_TOO_LARGE, "Tệp tải lên vượt quá giới hạn cho phép.",
                List.of(new ApiFieldError("FILE_TOO_LARGE", "Tệp tải lên vượt quá giới hạn 50 MB.")), request);
    }

    @ExceptionHandler({NoHandlerFoundException.class, HttpRequestMethodNotSupportedException.class})
    ResponseEntity<ApiEnvelope<Void>> handleRoute(Exception exception, HttpServletRequest request) {
        return response(HttpStatus.NOT_FOUND, "Không tìm thấy tài nguyên yêu cầu.",
                List.of(new ApiFieldError("NOT_FOUND", "Không tìm thấy tài nguyên yêu cầu.")), request);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiEnvelope<Void>> handleUnknown(Exception exception, HttpServletRequest request) {
        log.error("Lỗi chưa được xử lý tại {} {} traceId={}", request.getMethod(), request.getRequestURI(),
                request.getAttribute("traceId"), exception);
        return response(HttpStatus.INTERNAL_SERVER_ERROR, "Hệ thống đang gặp sự cố. Vui lòng thử lại sau.",
                List.of(new ApiFieldError("INTERNAL_ERROR", "Hệ thống đang gặp sự cố. Vui lòng thử lại sau.")), request);
    }

    private ResponseEntity<ApiEnvelope<Void>> response(HttpStatus status, String message,
                                                       List<ApiFieldError> errors, HttpServletRequest request) {
        String traceId = (String) request.getAttribute("traceId");
        return ResponseEntity.status(status).body(ApiEnvelope.failure(message, errors, traceId));
    }
}
