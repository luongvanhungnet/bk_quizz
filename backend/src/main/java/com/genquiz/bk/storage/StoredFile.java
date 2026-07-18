package com.genquiz.bk.storage;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name="stored_files")
public class StoredFile {
    @Id private UUID id;
    @Column(name="owner_id") private UUID ownerId;
    @Enumerated(EnumType.STRING) @Column(nullable=false,length=40) private Purpose purpose;
    @Enumerated(EnumType.STRING) @Column(nullable=false,length=20) private Provider provider;
    @Column(name="storage_path",nullable=false,length=1000) private String storagePath;
    @Column(name="original_name",nullable=false,length=255) private String originalName;
    @Column(name="declared_media_type",length=255) private String declaredMediaType;
    @Column(name="detected_media_type",nullable=false,length=255) private String detectedMediaType;
    @Column(name="size_bytes",nullable=false) private long sizeBytes;
    @Column(nullable=false,length=64) private String sha256;
    @Enumerated(EnumType.STRING) @Column(nullable=false,length=20) private Status status;
    @Column(name="public_access",nullable=false) private boolean publicAccess;
    @Column(name="created_at",nullable=false,updatable=false) private Instant createdAt;
    @Column(name="updated_at",nullable=false) private Instant updatedAt;
    @Column(name="deleted_at") private Instant deletedAt;
    @Version private long version;
    protected StoredFile() {}
    public StoredFile(UUID ownerId,Purpose purpose,Provider provider,String path,String name,String declared,String detected,long size,String sha256,boolean publicAccess){
        this.id=UUID.randomUUID();this.ownerId=ownerId;this.purpose=purpose;this.provider=provider;this.storagePath=path;
        this.originalName=name;this.declaredMediaType=declared;this.detectedMediaType=detected;this.sizeBytes=size;
        this.sha256=sha256;this.publicAccess=publicAccess;this.status=Status.READY;this.createdAt=Instant.now();this.updatedAt=createdAt;
    }
    public void quarantine(){status=Status.QUARANTINED;updatedAt=Instant.now();}
    public void restore(){status=Status.READY;updatedAt=Instant.now();}
    public void softDelete(){status=Status.DELETED;deletedAt=Instant.now();updatedAt=deletedAt;}
    public UUID getId(){return id;} public UUID getOwnerId(){return ownerId;} public Purpose getPurpose(){return purpose;}
    public Provider getProvider(){return provider;} public String getStoragePath(){return storagePath;} public String getOriginalName(){return originalName;}
    public String getDeclaredMediaType(){return declaredMediaType;} public String getDetectedMediaType(){return detectedMediaType;}
    public long getSizeBytes(){return sizeBytes;} public String getSha256(){return sha256;} public Status getStatus(){return status;}
    public boolean isPublicAccess(){return publicAccess;} public Instant getCreatedAt(){return createdAt;} public long getVersion(){return version;}
    public Instant getUpdatedAt(){return updatedAt;} public Instant getDeletedAt(){return deletedAt;}
    public enum Purpose { SOURCE, CLASSROOM_ATTACHMENT, AVATAR }
    public enum Provider { LOCAL, S3 }
    public enum Status { STAGED, READY, QUARANTINED, DELETED }
}
