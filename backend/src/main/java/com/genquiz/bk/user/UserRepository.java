package com.genquiz.bk.user;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;
import java.util.UUID;

public interface UserRepository extends JpaRepository<User, UUID> {
    Optional<User> findByEmailIgnoreCaseAndDeletedAtIsNull(String email);
    boolean existsByEmailIgnoreCase(String email);
    Optional<User> findByIdAndDeletedAtIsNull(UUID id);

    @Query("select u from User u where u.deletedAt is null and " +
            "(lower(u.email) like lower(concat('%', :search, '%')) or lower(u.username) like lower(concat('%', :search, '%')))")
    Page<User> search(String search, Pageable pageable);
}
