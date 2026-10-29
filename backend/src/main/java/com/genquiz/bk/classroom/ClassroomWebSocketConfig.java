package com.genquiz.bk.classroom;

import com.genquiz.bk.security.JwtService;
import com.genquiz.bk.config.AppProperties;
import java.util.List;
import java.util.UUID;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
@ConditionalOnProperty(name = "bkquiz.realtime.provider", havingValue = "stomp", matchIfMissing = true)
public class ClassroomWebSocketConfig implements WebSocketMessageBrokerConfigurer {
    private final JwtService jwt;
    private final ClassroomMemberRepository members;
    private final AppProperties properties;

    public ClassroomWebSocketConfig(JwtService jwt, ClassroomMemberRepository members, AppProperties properties) {
        this.jwt = jwt;
        this.members = members;
        this.properties = properties;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic");
        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws").setAllowedOrigins(properties.frontendOrigins().toArray(String[]::new));
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {
            @Override public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
                if (accessor.getCommand() == StompCommand.CONNECT) authenticate(accessor);
                if (accessor.getCommand() == StompCommand.SUBSCRIBE) authorizeSubscription(accessor);
                return message;
            }
        });
    }

    private void authenticate(StompHeaderAccessor accessor) {
        String authorization = accessor.getFirstNativeHeader("Authorization");
        if (authorization == null || !authorization.startsWith("Bearer ")) throw new IllegalArgumentException("Missing access token");
        JwtService.AccessClaims claims = jwt.verifyAccessToken(authorization.substring(7));
        accessor.setUser(new UsernamePasswordAuthenticationToken(claims.userId().toString(), null,
                List.of(new SimpleGrantedAuthority("ROLE_" + claims.role().name()))));
    }

    private void authorizeSubscription(StompHeaderAccessor accessor) {
        String destination = accessor.getDestination();
        if (destination == null || !destination.startsWith("/topic/classrooms/")) return;
        if (accessor.getUser() == null) throw new IllegalArgumentException("Missing authentication");
        UUID classroomId = UUID.fromString(destination.substring("/topic/classrooms/".length()));
        UUID userId = UUID.fromString(accessor.getUser().getName());
        if (!members.existsByClassroomIdAndUserIdAndStatus(classroomId, userId, ClassroomMemberStatus.ACTIVE)) {
            throw new IllegalArgumentException("Not a classroom member");
        }
    }
}
