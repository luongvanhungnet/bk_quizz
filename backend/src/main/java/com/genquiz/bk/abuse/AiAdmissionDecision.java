package com.genquiz.bk.abuse;

public enum AiAdmissionDecision {
    ALLOWED,
    USER_RATE_LIMIT,
    IP_RATE_LIMIT,
    DEVICE_RATE_LIMIT,
    DAILY_QUOTA,
    COST_BUDGET,
    USER_CONCURRENCY,
    IP_CONCURRENCY,
    DEVICE_CONCURRENCY
}
