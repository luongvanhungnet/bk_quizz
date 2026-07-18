package com.genquiz.bk.security;

import com.genquiz.bk.config.AppProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.header.writers.PermissionsPolicyHeaderWriter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder(AppProperties properties) {
        return new BCryptPasswordEncoder(properties.security().bcryptStrength());
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource(AppProperties properties) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(properties.frontendOrigins());
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type", "Idempotency-Key", "X-XSRF-TOKEN", "X-Request-Id"));
        cors.setExposedHeaders(List.of("X-Request-Id", "Location"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, JwtAuthenticationFilter jwtFilter,
                                            CookieCsrfFilter csrfFilter,
                                            JsonAuthenticationEntryPoint entryPoint,
                                            JsonAccessDeniedHandler deniedHandler) throws Exception {
        http
                .cors(Customizer.withDefaults())
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .headers(headers -> {
                    headers.contentTypeOptions(Customizer.withDefaults());
                    headers.frameOptions(frame -> frame.deny());
                    headers.referrerPolicy(referrer -> referrer.policy(
                            org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER));
                    headers.addHeaderWriter(new PermissionsPolicyHeaderWriter(
                            "camera=(), microphone=(), geolocation=()"));
                    headers.contentSecurityPolicy(csp -> csp.policyDirectives(
                            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"));
                })
                .exceptionHandling(errors -> errors.authenticationEntryPoint(entryPoint).accessDeniedHandler(deniedHandler))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/ws/**").permitAll()
                        .requestMatchers("/api/health", "/api/docs/**", "/api/openapi.json/**", "/actuator/health/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/explore/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/avatars/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/local-files/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/classrooms/join/*/preview").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/register", "/api/auth/login",
                                "/api/auth/refresh-token", "/api/auth/verify-email", "/api/auth/verify-email/resend",
                                "/api/auth/forgot-password", "/api/auth/reset-password", "/api/auth/cancel-deletion").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .addFilterBefore(csrfFilter, UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
