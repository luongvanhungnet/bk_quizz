package com.genquiz.bk.community;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface QuizStatisticsRepository extends JpaRepository<QuizStatistics, UUID> {}
