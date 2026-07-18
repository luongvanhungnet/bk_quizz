package com.genquiz.bk.auth;

import com.genquiz.bk.auth.dto.AuthPayload;
import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserService;
import com.genquiz.bk.user.dto.ChangeAccountTypeRequest;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users/me")
public class AccountTypeController {
    private final UserService users;
    private final AuthService auth;
    private final AppProperties properties;
    private final TokenHashService tokenHashes;

    public AccountTypeController(UserService users, AuthService auth, AppProperties properties, TokenHashService tokenHashes) {
        this.users = users; this.auth = auth; this.properties = properties; this.tokenHashes = tokenHashes;
    }

    @PostMapping("/account-type")
    ApiEnvelope<AuthPayload> change(@Valid @RequestBody ChangeAccountTypeRequest request,
                                    HttpServletRequest servletRequest, HttpServletResponse response) {
        User user = users.changeAccountType(request);
        String forwarded = servletRequest.getHeader("X-Forwarded-For");
        String ip = forwarded == null ? servletRequest.getRemoteAddr() : forwarded.split(",", 2)[0].trim();
        String agent = servletRequest.getHeader("User-Agent");
        AuthService.IssuedSession issued = auth.issueReplacementSession(user,
                new AuthService.ClientMetadata(ip, agent == null || agent.length() <= 500 ? agent : agent.substring(0, 500)));
        setCookies(response, issued.refreshToken());
        return ApiEnvelope.success("Đổi loại tài khoản thành công.", issued.payload());
    }

    private void setCookies(HttpServletResponse response, String refreshToken) {
        AppProperties.Security security = properties.security();
        response.addHeader(HttpHeaders.SET_COOKIE, ResponseCookie.from(security.refreshCookieName(), refreshToken)
                .httpOnly(true).secure(security.cookieSecure()).sameSite("Lax").path("/api/auth")
                .maxAge(security.refreshTtl()).build().toString());
        response.addHeader(HttpHeaders.SET_COOKIE, ResponseCookie.from(security.xsrfCookieName(), tokenHashes.newSecret())
                .httpOnly(false).secure(security.cookieSecure()).sameSite("Lax").path("/")
                .maxAge(security.refreshTtl()).build().toString());
    }
}
