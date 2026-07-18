package com.genquiz.bk.classroom;
import jakarta.persistence.*; import java.time.Instant; import java.util.UUID;
@Entity @Table(name="classroom_topic_shares")
public class ClassroomTopicShare {
 @Id private UUID id; @Column(name="classroom_id",nullable=false) private UUID classroomId;
 @Column(name="topic_id",nullable=false) private UUID topicId; @Column(name="shared_by",nullable=false) private UUID sharedBy;
 @Column(name="created_at",nullable=false) private Instant createdAt; @Column(name="revoked_at") private Instant revokedAt;
 @Version private long version; protected ClassroomTopicShare(){}
 public ClassroomTopicShare(UUID classroomId,UUID topicId,UUID sharedBy,Instant now){id=UUID.randomUUID();this.classroomId=classroomId;this.topicId=topicId;this.sharedBy=sharedBy;createdAt=now;}
 public void revoke(Instant now){revokedAt=now;} public UUID getId(){return id;} public UUID getClassroomId(){return classroomId;}
 public UUID getTopicId(){return topicId;} public UUID getSharedBy(){return sharedBy;} public Instant getCreatedAt(){return createdAt;} public Instant getRevokedAt(){return revokedAt;}
}
