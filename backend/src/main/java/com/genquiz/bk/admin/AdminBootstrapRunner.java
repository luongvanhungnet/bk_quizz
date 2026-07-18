package com.genquiz.bk.admin;

import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserPreferences;
import com.genquiz.bk.user.UserPreferencesRepository;
import com.genquiz.bk.user.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;

@Component
@ConditionalOnProperty(name = "bkquiz.admin-bootstrap.enabled", havingValue = "true")
public class AdminBootstrapRunner implements ApplicationRunner {
    private static final Logger log = LoggerFactory.getLogger(AdminBootstrapRunner.class);
    private final UserRepository users;
    private final UserPreferencesRepository preferences;
    private final PasswordEncoder passwords;
    private final String email;
    private final String username;
    private final String password;

    public AdminBootstrapRunner(UserRepository users, UserPreferencesRepository preferences, PasswordEncoder passwords,
                                @Value("${bkquiz.admin-bootstrap.email}") String email,
                                @Value("${bkquiz.admin-bootstrap.username}") String username,
                                @Value("${bkquiz.admin-bootstrap.password}") String password) {
        this.users = users; this.preferences = preferences; this.passwords = passwords;
        this.email = email; this.username = username; this.password = password;
    }

    @Override @Transactional
    public void run(ApplicationArguments args) {
        if (email.isBlank() || password.length() < 12) {
            throw new IllegalStateException("ADMIN_BOOTSTRAP_EMAIL và mật khẩu tối thiểu 12 ký tự là bắt buộc.");
        }
        String normalized = email.trim().toLowerCase(Locale.ROOT);
        User admin = users.findByEmailIgnoreCaseAndDeletedAtIsNull(normalized).orElseGet(() -> {
            User created = users.save(new User(username.trim(), normalized, passwords.encode(password)));
            preferences.save(new UserPreferences(created));
            return created;
        });
        admin.setRole(Role.ADMIN);
        admin.setActive(true);
        if (!admin.isEmailVerified()) admin.verifyEmail();
        log.info("Đã bảo đảm tài khoản bootstrap admin tồn tại cho miền email {}.", normalized.substring(normalized.indexOf('@') + 1));
    }
}
