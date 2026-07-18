package com.genquiz.bk.security;

import tools.jackson.databind.ObjectMapper;
import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.ApiFieldError;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

@Component
public class JsonAccessDeniedHandler implements AccessDeniedHandler {
    private final ObjectMapper objectMapper;
    public JsonAccessDeniedHandler(ObjectMapper objectMapper) { this.objectMapper = objectMapper; }
    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response,
                       AccessDeniedException accessDeniedException) throws IOException {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        objectMapper.writeValue(response.getWriter(), ApiEnvelope.failure("Bạn không có quyền thực hiện thao tác này.",
                List.of(new ApiFieldError("ACCESS_DENIED", "Bạn không có quyền thực hiện thao tác này.")),
                (String) request.getAttribute("traceId")));
    }
}
