package com.genquiz.bk.auth;

import com.genquiz.bk.auth.dto.AuthPayload;
import com.genquiz.bk.auth.dto.ForgotPasswordRequest;
import com.genquiz.bk.auth.dto.LoginRequest;
import com.genquiz.bk.auth.dto.RegisterRequest;
import com.genquiz.bk.auth.dto.ResetPasswordRequest;
import com.genquiz.bk.auth.dto.TokenRequest;
import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.security.CurrentUser;
import com.genquiz.bk.user.dto.UserDto;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.Cookie;
import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Duration;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthService auth;
    private final CurrentUser currentUser;
    private final AppProperties properties;
    private final TokenHashService tokenHashes;

    public AuthController(AuthService auth, CurrentUser currentUser, AppProperties properties,
                          TokenHashService tokenHashes) {
        this.auth = auth;
        this.currentUser = currentUser;
        this.properties = properties;
        this.tokenHashes = tokenHashes;
    }

    @PostMapping("/register")
    ResponseEntity<ApiEnvelope<AuthPayload>> register(@Valid @RequestBody RegisterRequest request,
                                                       HttpServletRequest servletRequest,
                                                       HttpServletResponse response) {
        AuthService.IssuedSession issued = auth.register(request, metadata(servletRequest));
        setSessionCookies(response, issued.refreshToken());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiEnvelope.success("Đăng ký tài khoản thành công. Vui lòng kiểm tra email để xác minh.",
                        issued.payload()));
    }

    @PostMapping("/login")
    ApiEnvelope<AuthPayload> login(@Valid @RequestBody LoginRequest request,
                                   HttpServletRequest servletRequest, HttpServletResponse response) {
        AuthService.IssuedSession issued = auth.login(request, metadata(servletRequest));
        setSessionCookies(response, issued.refreshToken());
        return ApiEnvelope.success("Đăng nhập thành công.", issued.payload());
    }

    @PostMapping("/refresh-token")
    ApiEnvelope<AuthPayload> refresh(
            HttpServletRequest servletRequest, HttpServletResponse response) {
        String refreshToken = cookie(servletRequest, properties.security().refreshCookieName());
        AuthService.IssuedSession issued = auth.refresh(refreshToken, metadata(servletRequest));
        setSessionCookies(response, issued.refreshToken());
        return ApiEnvelope.success("Làm mới phiên đăng nhập thành công.", issued.payload());
    }

    @PostMapping("/logout")
    ApiEnvelope<Void> logout(HttpServletRequest request, HttpServletResponse response) {
        String refreshToken = cookie(request, properties.security().refreshCookieName());
        auth.logout(refreshToken);
        clearSessionCookies(response);
        return ApiEnvelope.success("Đăng xuất thành công.", null);
    }

    @PostMapping("/logout-all")
    ApiEnvelope<Void> logoutAll(HttpServletResponse response) {
        auth.logoutAll(currentUser.id());
        clearSessionCookies(response);
        return ApiEnvelope.success("Đã đăng xuất khỏi tất cả thiết bị.", null);
    }

    @GetMapping("/me")
    ApiEnvelope<UserDto> me() {
        return ApiEnvelope.success("Lấy thông tin tài khoản thành công.", UserDto.from(currentUser.require()));
    }

    @PostMapping("/verify-email")
    ApiEnvelope<Void> verifyEmail(@Valid @RequestBody TokenRequest request) {
        auth.confirmEmail(request.token());
        return ApiEnvelope.success("Xác minh email thành công.", null);
    }

    @PostMapping("/verify-email/resend")
    ApiEnvelope<Void> resend(@Valid @RequestBody ForgotPasswordRequest request) {
        auth.resendVerification(request);
        return ApiEnvelope.success("Nếu tài khoản phù hợp, email xác minh mới đã được gửi.", null);
    }

    @PostMapping("/forgot-password")
    ApiEnvelope<Void> forgot(@Valid @RequestBody ForgotPasswordRequest request) {
        auth.forgotPassword(request);
        return ApiEnvelope.success("Nếu email tồn tại, hướng dẫn đặt lại mật khẩu đã được gửi.", null);
    }

    @PostMapping("/reset-password")
    ApiEnvelope<Void> reset(@Valid @RequestBody ResetPasswordRequest request) {
        auth.resetPassword(request);
        return ApiEnvelope.success("Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại.", null);
    }

    private AuthService.ClientMetadata metadata(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        String ip = forwarded == null ? request.getRemoteAddr() : forwarded.split(",", 2)[0].trim();
        return new AuthService.ClientMetadata(ip, truncate(request.getHeader("User-Agent"), 500));
    }

    private void setSessionCookies(HttpServletResponse response, String refreshToken) {
        AppProperties.Security security = properties.security();
        response.addHeader(HttpHeaders.SET_COOKIE, ResponseCookie.from(security.refreshCookieName(), refreshToken)
                .httpOnly(true).secure(security.cookieSecure()).sameSite("Lax").path("/api/auth")
                .maxAge(security.refreshTtl()).build().toString());
        String xsrf = tokenHashes.newSecret();
        response.addHeader(HttpHeaders.SET_COOKIE, ResponseCookie.from(security.xsrfCookieName(), xsrf)
                .httpOnly(false).secure(security.cookieSecure()).sameSite("Lax").path("/")
                .maxAge(security.refreshTtl()).build().toString());
    }

    private void clearSessionCookies(HttpServletResponse response) {
        response.addHeader(HttpHeaders.SET_COOKIE, expired(properties.security().refreshCookieName(), "/", true));
        response.addHeader(HttpHeaders.SET_COOKIE, expired(properties.security().refreshCookieName(), "/api/auth", true));
        response.addHeader(HttpHeaders.SET_COOKIE, expired(properties.security().xsrfCookieName(), "/", false));
    }

    private String expired(String name, String path, boolean httpOnly) {
        return ResponseCookie.from(name, "").path(path).httpOnly(httpOnly)
                .secure(properties.security().cookieSecure()).sameSite("Lax").maxAge(Duration.ZERO).build().toString();
    }

    private String truncate(String value, int max) {
        return value == null || value.length() <= max ? value : value.substring(0, max);
    }

    private String cookie(HttpServletRequest request, String name) {
        if (request.getCookies() == null) return null;
        for (Cookie candidate : request.getCookies()) if (name.equals(candidate.getName())) return candidate.getValue();
        return null;
    }
}
