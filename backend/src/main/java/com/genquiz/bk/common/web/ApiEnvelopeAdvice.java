package com.genquiz.bk.common.web;

import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.PageMetadata;
import org.springframework.core.MethodParameter;
import org.springframework.core.io.Resource;
import org.springframework.data.domain.Page;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@ControllerAdvice(basePackages = "com.genquiz.bk")
public class ApiEnvelopeAdvice implements ResponseBodyAdvice<Object> {
    @Override
    public boolean supports(MethodParameter returnType, Class<? extends HttpMessageConverter<?>> converterType) {
        return true;
    }

    @Override
    public Object beforeBodyWrite(Object body, MethodParameter returnType, MediaType selectedContentType,
                                  Class<? extends HttpMessageConverter<?>> selectedConverterType,
                                  ServerHttpRequest request, ServerHttpResponse response) {
        String path = request.getURI().getPath();
        if (!path.startsWith("/api/") || path.startsWith("/api/docs") || path.startsWith("/api/openapi")) return body;
        if (body instanceof ApiEnvelope<?> || body instanceof Resource || body instanceof byte[]
                || body instanceof StreamingResponseBody) return body;
        if (body instanceof Page<?> page) {
            return ApiEnvelope.page("Lấy dữ liệu thành công.", page.getContent(), new PageMetadata(
                    page.getNumber() + 1, page.getSize(), page.getTotalElements(), page.getTotalPages(),
                    page.hasNext(), page.hasPrevious()));
        }
        return ApiEnvelope.success("Thao tác thành công.", body);
    }
}

