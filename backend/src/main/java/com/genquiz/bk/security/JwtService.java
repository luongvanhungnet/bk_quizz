package com.genquiz.bk.security;

import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jose.crypto.MACVerifier;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.text.ParseException;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Set;
import java.util.UUID;

@Component
public class JwtService {
    private final byte[] secret;
    private final AppProperties properties;

    public JwtService(AppProperties properties) {
        this.properties = properties;
        this.secret = properties.security().accessSecret().getBytes(StandardCharsets.UTF_8);
    }

    public String issueAccessToken(User user) {
        Set<String> roles = user.getRole() == Role.ADMIN ? Set.of("USER", "ADMIN") : Set.of("USER");
        return issueAccessToken(user, new AuthorizationService.AuthorizationSnapshot(roles, Set.of()));
    }

    public String issueAccessToken(User user, AuthorizationService.AuthorizationSnapshot authorization) {
        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .subject(user.getId().toString())
                .issuer("bkquiz-api")
                .audience("bkquiz-frontend")
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plus(properties.security().accessTtl())))
                .jwtID(UUID.randomUUID().toString())
                .claim("type", "access")
                .claim("email", user.getEmail())
                .claim("role", user.getRole().name())
                .claim("roles", authorization.roles().stream().sorted().toList())
                .claim("permissions", authorization.permissions().stream().sorted().toList())
                .claim("emailVerified", user.isEmailVerified())
                .build();
        SignedJWT jwt = new SignedJWT(new JWSHeader(JWSAlgorithm.HS256), claims);
        try {
            jwt.sign(new MACSigner(secret));
            return jwt.serialize();
        } catch (JOSEException exception) {
            throw new IllegalStateException("Không thể tạo access token.", exception);
        }
    }

    public AccessClaims verifyAccessToken(String token) {
        try {
            SignedJWT jwt = SignedJWT.parse(token);
            if (!JWSAlgorithm.HS256.equals(jwt.getHeader().getAlgorithm()) || !jwt.verify(new MACVerifier(secret))) {
                throw new JwtValidationException();
            }
            JWTClaimsSet claims = jwt.getJWTClaimsSet();
            if (!"access".equals(claims.getStringClaim("type")) ||
                    claims.getExpirationTime() == null || claims.getExpirationTime().before(new Date())) {
                throw new JwtValidationException();
            }
            return new AccessClaims(UUID.fromString(claims.getSubject()),
                    Role.valueOf(claims.getStringClaim("role")),
                    claims.getStringClaim("email"),
                    stringSet(claims.getStringListClaim("roles")),
                    stringSet(claims.getStringListClaim("permissions")));
        } catch (ParseException | JOSEException | IllegalArgumentException exception) {
            throw new JwtValidationException();
        }
    }

    public long accessTtlSeconds() { return properties.security().accessTtl().toSeconds(); }

    private Set<String> stringSet(List<String> values) {
        return values == null ? Set.of() : Set.copyOf(values);
    }

    public record AccessClaims(UUID userId, Role role, String email,
                               Set<String> roles, Set<String> permissions) {}

    public static final class JwtValidationException extends RuntimeException {}
}
