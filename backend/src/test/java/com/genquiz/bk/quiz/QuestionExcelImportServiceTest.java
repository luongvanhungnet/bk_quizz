package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import com.genquiz.bk.common.error.ApiException;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

class QuestionExcelImportServiceTest {

    @Test
    void rejectsLegacyOrMacroExcelFilesBeforeParsing() {
        QuestionService questions = mock(QuestionService.class);
        QuestionExcelImportService service = new QuestionExcelImportService(
                new QuestionExcelWorkbook(), questions);
        var file = new MockMultipartFile("file", "questions.xlsm",
                "application/vnd.ms-excel.sheet.macroEnabled.12", new byte[] {1, 2, 3});

        ApiException error = assertThrows(ApiException.class,
                () -> service.importFile(UUID.randomUUID(), UUID.randomUUID(), file));

        assertEquals("EXCEL_FILE_INVALID", error.code());
        verifyNoInteractions(questions);
    }
}
