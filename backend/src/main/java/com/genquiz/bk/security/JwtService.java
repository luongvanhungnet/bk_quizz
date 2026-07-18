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
                    claims.getStringClaim("email"));
        } catch (ParseException | JOSEException | IllegalArgumentException exception) {
            throw new JwtValidationException();
        }
    }

    public long accessTtlSeconds() { return properties.security().accessTtl().toSeconds(); }

    public record AccessClaims(UUID userId, Role role, String email) {}

    public static final class JwtValidationException extends RuntimeException {}
}

