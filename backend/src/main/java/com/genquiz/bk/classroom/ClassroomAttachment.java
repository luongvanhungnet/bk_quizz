package com.genquiz.bk.classroom;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity @Table(name="classroom_attachments")
public class ClassroomAttachment {
    @Id private UUID id;
    @Column(name="classroom_id",nullable=false,updatable=false) private UUID classroomId;
    @Column(name="uploader_id",nullable=false,updatable=false) private UUID uploaderId;
    @Column(name="message_id") private UUID messageId;
    @Column(name="object_key",nullable=false,length=1000) private String objectKey;
    @Column(name="file_id") private UUID fileId;
    @Column(name="original_name",nullable=false,length=255) private String originalName;
    @Column(name="media_type",nullable=false,length=255) private String mediaType;
    @Column(name="size_bytes",nullable=false) private long sizeBytes;
    @Column(nullable=false) private boolean image;
    @Column(nullable=false,length=20) private String status="READY";
    @Column(name="expires_at") private Instant expiresAt;
    @Column(name="created_at",nullable=false,updatable=false) private Instant createdAt;
    protected ClassroomAttachment() {}
    public ClassroomAttachment(UUID classroomId, UUID uploaderId, String key, String name, String mediaType,
                               long size, boolean image, Instant now){this.id=UUID.randomUUID();this.classroomId=classroomId;
        this.uploaderId=uploaderId;this.objectKey=key;this.originalName=name;this.mediaType=mediaType;this.sizeBytes=size;
        this.image=image;this.createdAt=now;this.expiresAt=now.plusSeconds(3600);}
    public void attach(UUID messageId){this.messageId=messageId;this.status="ATTACHED";this.expiresAt=null;}
    public UUID getId(){return id;} public UUID getClassroomId(){return classroomId;} public UUID getUploaderId(){return uploaderId;}
    public UUID getMessageId(){return messageId;} public String getObjectKey(){return objectKey;} public String getOriginalName(){return originalName;}
    public UUID getFileId(){return fileId;} public void attachFile(UUID value){fileId=value;}
    public String getMediaType(){return mediaType;} public long getSizeBytes(){return sizeBytes;} public boolean isImage(){return image;}
    public Instant getExpiresAt(){return expiresAt;}
}
