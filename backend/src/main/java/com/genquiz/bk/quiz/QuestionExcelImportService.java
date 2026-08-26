package com.genquiz.bk.quiz;

import com.genquiz.bk.common.api.ApiFieldError;
import com.genquiz.bk.common.error.ApiException;
import java.io.IOException;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class QuestionExcelImportService {
    static final long MAX_FILE_SIZE = 5L * 1024 * 1024;
    private static final Set<String> ACCEPTED_TYPES = Set.of(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/octet-stream");
    private final QuestionExcelWorkbook workbook;
    private final QuestionService questions;

    @Autowired
    public QuestionExcelImportService(QuestionService questions) {
        this(new QuestionExcelWorkbook(), questions);
    }

    QuestionExcelImportService(QuestionExcelWorkbook workbook, QuestionService questions) {
        this.workbook = workbook;
        this.questions = questions;
    }

    public byte[] template() {
        return workbook.template();
    }

    public QuizDtos.QuestionImportResponse importFile(
            UUID actorId, UUID quizId, MultipartFile file) {
        validateFile(file);
        try {
            return questions.importQuestions(actorId, quizId, workbook.parseRows(file.getBytes()));
        } catch (IOException exception) {
            throw invalid("Không thể đọc file Excel đã tải lên.");
        }
    }

    private static void validateFile(MultipartFile file) {
        String filename = file == null || file.getOriginalFilename() == null
                ? "" : file.getOriginalFilename().trim().toLowerCase(Locale.ROOT);
        String contentType = file == null || file.getContentType() == null
                ? "" : file.getContentType().trim().toLowerCase(Locale.ROOT);
        if (file == null || file.isEmpty() || !filename.endsWith(".xlsx")
                || (!contentType.isBlank() && !ACCEPTED_TYPES.contains(contentType))) {
            throw invalid("Chỉ chấp nhận file Excel .xlsx hợp lệ.");
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw new ApiException(HttpStatus.CONTENT_TOO_LARGE, "EXCEL_FILE_TOO_LARGE",
                    "File Excel vượt quá giới hạn 5 MB.", List.of(new ApiFieldError(
                    "EXCEL_FILE_TOO_LARGE", "file", "File Excel không được vượt quá 5 MB.")));
        }
    }

    private static ApiException invalid(String message) {
        return new ApiException(HttpStatus.UNPROCESSABLE_CONTENT, "EXCEL_FILE_INVALID", message,
                List.of(new ApiFieldError("EXCEL_FILE_INVALID", "file", message)));
    }
}
