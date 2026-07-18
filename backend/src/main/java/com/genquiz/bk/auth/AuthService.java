package com.genquiz.bk.auth;

import com.genquiz.bk.auth.dto.AuthPayload;
import com.genquiz.bk.auth.dto.ForgotPasswordRequest;
import com.genquiz.bk.auth.dto.LoginRequest;
import com.genquiz.bk.auth.dto.RegisterRequest;
import com.genquiz.bk.auth.dto.ResetPasswordRequest;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.security.JwtService;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserPreferences;
import com.genquiz.bk.user.UserPreferencesRepository;
import com.genquiz.bk.user.UserRepository;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.dto.UserDto;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

@Service
public class AuthService {
    private static final Duration VERIFY_TTL = Duration.ofHours(24);
    private static final Duration RESET_TTL = Duration.ofMinutes(15);

    private final UserRepository users;
    private final UserPreferencesRepository preferences;
    private final RefreshSessionRepository sessions;
    private final EmailVerificationTokenRepository verificationTokens;
    private final PasswordResetTokenRepository resetTokens;
    private final PasswordEncoder passwordEncoder;
    private final TokenHashService tokenHashes;
    private final JwtService jwt;
    private final AppProperties properties;
    private final AuthMailQueue mailQueue;

    public AuthService(UserRepository users, UserPreferencesRepository preferences,
                       RefreshSessionRepository sessions,
                       EmailVerificationTokenRepository verificationTokens,
                       PasswordResetTokenRepository resetTokens,
                       PasswordEncoder passwordEncoder, TokenHashService tokenHashes,
                       JwtService jwt, AppProperties properties, AuthMailQueue mailQueue) {
        this.users = users;
        this.preferences = preferences;
        this.sessions = sessions;
        this.verificationTokens = verificationTokens;
        this.resetTokens = resetTokens;
        this.passwordEncoder = passwordEncoder;
        this.tokenHashes = tokenHashes;
        this.jwt = jwt;
        this.properties = properties;
        this.mailQueue = mailQueue;
    }

    @Transactional
    public IssuedSession register(RegisterRequest request, ClientMetadata client) {
        String email = normalizeEmail(request.email());
        if (users.existsByEmailIgnoreCase(email)) {
            throw new ApiException(HttpStatus.CONFLICT, "EMAIL_ALREADY_EXISTS", "Email đã được sử dụng.");
        }
        User user = new User(request.username().trim(), email, passwordEncoder.encode(request.password()));
        user.setRole(request.accountType() == RegisterRequest.AccountType.TEACHER ? Role.TEACHER : Role.STUDENT);
        user = users.save(user);
        preferences.save(new UserPreferences(user));
        issueVerificationEmail(user);
        return newSession(user, UUID.randomUUID(), client);
    }

    @Transactional
    public IssuedSession login(LoginRequest request, ClientMetadata client) {
        User user = users.findByEmailIgnoreCaseAndDeletedAtIsNull(normalizeEmail(request.email()))
                .orElseThrow(AuthService::invalidCredentials);
        if (!passwordEncoder.matches(request.password(), user.getPasswordHash())) throw invalidCredentials();
        if (!user.isActive()) {
            String code = user.getDeletionRequestedAt() != null ? "ACCOUNT_PENDING_DELETION" : "ACCOUNT_INACTIVE";
            String message = user.getDeletionRequestedAt() != null
                    ? "Tài khoản đang chờ xóa. Hãy dùng liên kết trong email để hủy yêu cầu."
                    : "Tài khoản đã bị khóa.";
            throw new ApiException(HttpStatus.FORBIDDEN, code, message);
        }
        return newSession(user, UUID.randomUUID(), client);
    }

    @Transactional
    public IssuedSession refresh(String rawToken, ClientMetadata client) {
        ParsedRefresh parsed = parseRefresh(rawToken);
        RefreshSession current = sessions.findByIdForUpdate(parsed.id())
                .orElseThrow(AuthService::invalidRefresh);
        if (!tokenHashes.matches(parsed.secret(), current.getTokenHash())) throw invalidRefresh();

        Instant now = Instant.now();
        if (current.getRevokedAt() != null || current.getReplacedById() != null) {
            sessions.revokeFamily(current.getFamilyId(), now);
            throw new ApiException(HttpStatus.UNAUTHORIZED, "REFRESH_TOKEN_REUSED",
                    "Phiên đăng nhập đã bị thu hồi do phát hiện token cũ được sử dụng lại.");
        }
        if (!current.isUsable(now) || !current.getUser().isActive()) {
            current.revoke();
            throw invalidRefresh();
        }

        IssuedSession replacement = newSession(current.getUser(), current.getFamilyId(), client);
        current.rotateTo(replacement.sessionId());
        sessions.save(current);
        return replacement;
    }

    @Transactional
    public void logout(String rawToken) {
        if (rawToken == null || rawToken.isBlank()) return;
        try {
            ParsedRefresh parsed = parseRefresh(rawToken);
            sessions.findByIdForUpdate(parsed.id()).ifPresent(session -> {
                if (tokenHashes.matches(parsed.secret(), session.getTokenHash())) session.revoke();
            });
        } catch (ApiException ignored) {
            // Logout intentionally remains idempotent and does not disclose token state.
        }
    }

    @Transactional
    public void logoutAll(UUID userId) { sessions.revokeAllForUser(userId, Instant.now()); }

    @Transactional
    public IssuedSession issueReplacementSession(User user, ClientMetadata client) {
        return newSession(user, UUID.randomUUID(), client);
    }

    @Transactional
    public void confirmEmail(String rawToken) {
        EmailVerificationToken token = verificationTokens.findByTokenHash(tokenHashes.hash(rawToken))
                .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST, "INVALID_VERIFICATION_TOKEN",
                        "Liên kết xác minh không hợp lệ hoặc đã hết hạn."));
        if (!token.isUsable()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_VERIFICATION_TOKEN",
                    "Liên kết xác minh không hợp lệ hoặc đã hết hạn.");
        }
        token.getUser().verifyEmail();
        token.use();
    }

    @Transactional
    public void resendVerification(ForgotPasswordRequest request) {
        users.findByEmailIgnoreCaseAndDeletedAtIsNull(normalizeEmail(request.email()))
                .filter(User::isActive)
                .filter(user -> !user.isEmailVerified())
                .ifPresent(this::issueVerificationEmail);
    }

    @Transactional
    public void forgotPassword(ForgotPasswordRequest request) {
        users.findByEmailIgnoreCaseAndDeletedAtIsNull(normalizeEmail(request.email()))
                .filter(User::isActive)
                .ifPresent(user -> {
                    resetTokens.deleteByUserId(user.getId());
                    String raw = tokenHashes.newSecret();
                    PasswordResetToken token = resetTokens.save(new PasswordResetToken(
                            user, tokenHashes.hash(raw), Instant.now().plus(RESET_TTL)));
                    mailQueue.enqueue(AuthMailEvent.Type.RESET_PASSWORD, user.getId(), token.getId(),
                            user.getEmail(), user.getUsername(), raw);
                });
    }

    @Transactional
    public void resetPassword(ResetPasswordRequest request) {
        PasswordResetToken token = resetTokens.findByTokenHash(tokenHashes.hash(request.token()))
                .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST, "INVALID_RESET_TOKEN",
                        "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn."));
        if (!token.isUsable()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_RESET_TOKEN",
                    "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.");
        }
        token.getUser().setPasswordHash(passwordEncoder.encode(request.password()));
        token.use();
        sessions.revokeAllForUser(token.getUser().getId(), Instant.now());
    }

    private void issueVerificationEmail(User user) {
        verificationTokens.deleteByUserId(user.getId());
        String raw = tokenHashes.newSecret();
        EmailVerificationToken token = verificationTokens.save(new EmailVerificationToken(
                user, tokenHashes.hash(raw), Instant.now().plus(VERIFY_TTL)));
        mailQueue.enqueue(AuthMailEvent.Type.VERIFY_EMAIL, user.getId(), token.getId(),
                user.getEmail(), user.getUsername(), raw);
    }

    private IssuedSession newSession(User user, UUID familyId, ClientMetadata client) {
        String secret = tokenHashes.newSecret();
        RefreshSession session = sessions.save(new RefreshSession(user, familyId, tokenHashes.hash(secret),
                Instant.now().plus(properties.security().refreshTtl()), client.userAgent(),
                client.ip() == null ? null : tokenHashes.hash(client.ip())));
        String rawRefresh = session.getId() + "." + secret;
        AuthPayload payload = new AuthPayload(jwt.issueAccessToken(user), jwt.accessTtlSeconds(), UserDto.from(user));
        return new IssuedSession(session.getId(), rawRefresh, payload);
    }

    private ParsedRefresh parseRefresh(String rawToken) {
        if (rawToken == null) throw invalidRefresh();
        String[] parts = rawToken.split("\\.", 2);
        if (parts.length != 2 || parts[1].isBlank()) throw invalidRefresh();
        try { return new ParsedRefresh(UUID.fromString(parts[0]), parts[1]); }
        catch (IllegalArgumentException exception) { throw invalidRefresh(); }
    }

    private static ApiException invalidCredentials() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "Email hoặc mật khẩu không chính xác.");
    }

    private static ApiException invalidRefresh() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_REFRESH_TOKEN",
                "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.");
    }

    private String normalizeEmail(String email) { return email.trim().toLowerCase(Locale.ROOT); }

    public record ClientMetadata(String ip, String userAgent) {}
    public record IssuedSession(UUID sessionId, String refreshToken, AuthPayload payload) {}
    private record ParsedRefresh(UUID id, String secret) {}
}
