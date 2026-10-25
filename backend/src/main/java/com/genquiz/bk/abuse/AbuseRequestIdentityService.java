package com.genquiz.bk.abuse;

import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Service;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

@Service
public class AbuseRequestIdentityService {
    private final byte[] secret;

    public AbuseRequestIdentityService(AntiAbuseProperties properties) {
        this.secret = properties.ipHashSecret().getBytes(StandardCharsets.UTF_8);
    }

    public AbuseRequestIdentity current() {
        var attributes = RequestContextHolder.getRequestAttributes();
        if (!(attributes instanceof ServletRequestAttributes servlet)) {
            return new AbuseRequestIdentity(hash("internal"), hash("internal-device"), null);
        }
        HttpServletRequest request = servlet.getRequest();
        String forwarded = request.getHeader("X-Forwarded-For");
        String ip = forwarded == null || forwarded.isBlank()
                ? request.getRemoteAddr() : forwarded.split(",", 2)[0].trim();
        String device = bounded(request.getHeader("X-Device-Id"), 160);
        if (device == null) {
            device = "derived:" + bounded(request.getHeader("User-Agent"), 300) + ":" + ip;
        }
        return new AbuseRequestIdentity(hash("ip:" + ip), hash("device:" + device),
                bounded(request.getHeader("X-Turnstile-Token"), 2048));
    }

    private String hash(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("Không thể tạo định danh chống lạm dụng.", exception);
        }
    }

    private static String bounded(String value, int max) {
        if (value == null || value.isBlank()) return null;
        String clean = value.replaceAll("[\\r\\n\\p{Cntrl}]", "").trim();
        return clean.substring(0, Math.min(max, clean.length()));
    }
}
