package com.genquiz.bk.auth;

import com.genquiz.bk.config.AppProperties;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

@Component
public class SensitivePayloadCipher {
    private static final byte[] PURPOSE = "bkquiz/auth-mail/v1".getBytes(StandardCharsets.UTF_8);
    private final SecretKeySpec key;
    private final SecureRandom random = new SecureRandom();

    public SensitivePayloadCipher(AppProperties properties) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(PURPOSE);
            this.key = new SecretKeySpec(digest.digest(
                    properties.security().accessSecret().getBytes(StandardCharsets.UTF_8)), "AES");
        } catch (Exception exception) {
            throw new IllegalStateException("Không thể khởi tạo mã hóa payload email.", exception);
        }
    }

    public String encrypt(String value) {
        try {
            byte[] iv = new byte[12]; random.nextBytes(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
            cipher.updateAAD(PURPOSE);
            byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(
                    ByteBuffer.allocate(iv.length + encrypted.length).put(iv).put(encrypted).array());
        } catch (Exception exception) {
            throw new IllegalStateException("Không thể mã hóa payload email.", exception);
        }
    }

    public String decrypt(String value) {
        try {
            byte[] all = Base64.getUrlDecoder().decode(value);
            byte[] iv = Arrays.copyOfRange(all, 0, 12);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
            cipher.updateAAD(PURPOSE);
            return new String(cipher.doFinal(Arrays.copyOfRange(all, 12, all.length)), StandardCharsets.UTF_8);
        } catch (Exception exception) {
            throw new IllegalStateException("Payload email không hợp lệ.", exception);
        }
    }
}
