package com.genquiz.bk.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ChangeAccountTypeRequest(@NotNull TargetRole targetRole, @NotBlank String password) {
    public enum TargetRole { STUDENT, TEACHER }
}
