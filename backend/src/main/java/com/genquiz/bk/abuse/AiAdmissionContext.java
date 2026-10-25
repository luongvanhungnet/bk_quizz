package com.genquiz.bk.abuse;

import java.math.BigDecimal;

public record AiAdmissionContext(String leaseId, String ipHash, String deviceHash, String endpoint,
                                 String model, BigDecimal estimatedCost, boolean concurrencyReserved) {}
