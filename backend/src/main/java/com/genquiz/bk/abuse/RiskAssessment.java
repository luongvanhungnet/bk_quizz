package com.genquiz.bk.abuse;

import java.util.List;

public record RiskAssessment(int trustScore, double riskScore, ServiceLevel serviceLevel,
                             List<Signal> signals) {
    public record Signal(String code, double contribution) {}
}
