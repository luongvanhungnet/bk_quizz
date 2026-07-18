package com.genquiz.bk.storage;

import com.genquiz.bk.common.error.ApiException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import java.io.BufferedInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

@Component
public class ClamAvScanner {
    private final String host;
    private final int port;
    private final boolean enabled;

    public ClamAvScanner(@Value("${bkquiz.storage.clamav-host:localhost}") String host,
                         @Value("${bkquiz.storage.clamav-port:3310}") int port,
                         @Value("${bkquiz.storage.clamav-enabled:false}") boolean enabled) {
        this.host = host; this.port = port; this.enabled = enabled;
    }

    public void requireClean(Path file) throws IOException {
        if (!enabled) return;
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 5000);
            socket.setSoTimeout(60000);
            try (DataOutputStream output = new DataOutputStream(socket.getOutputStream());
                 BufferedInputStream input = new BufferedInputStream(Files.newInputStream(file))) {
                output.write("zINSTREAM\0".getBytes(StandardCharsets.US_ASCII));
                byte[] buffer = new byte[8192];
                for (int read; (read = input.read(buffer)) >= 0;) {
                    if (read == 0) continue;
                    output.writeInt(read);
                    output.write(buffer, 0, read);
                }
                output.writeInt(0);
                output.flush();
                String response = new String(socket.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
                if (response.contains("FOUND")) {
                    throw new ApiException(HttpStatus.UNPROCESSABLE_CONTENT, "MALWARE_DETECTED",
                            "Tài liệu bị từ chối vì phát hiện nội dung không an toàn.");
                }
                if (!response.contains("OK")) throw new IOException("ClamAV không trả về trạng thái hợp lệ.");
            }
        }
    }
}
