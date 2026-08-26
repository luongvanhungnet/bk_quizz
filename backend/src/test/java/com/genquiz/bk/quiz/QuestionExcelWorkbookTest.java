package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.ByteArrayOutputStream;
import java.io.ByteArrayInputStream;
import java.util.List;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import com.genquiz.bk.common.error.ApiException;

class QuestionExcelWorkbookTest {

    @Test
    void templateSeparatesBlankImportSheetFromExamples() throws Exception {
        byte[] content = new QuestionExcelWorkbook().template();

        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(content))) {
            assertEquals(4, workbook.getNumberOfSheets());
            assertNotNull(workbook.getSheet("HuongDan"));
            assertNotNull(workbook.getSheet("CauHoi"));
            assertNotNull(workbook.getSheet("ViDu"));
            assertNotNull(workbook.getSheet("DanhMuc"));
            assertEquals(0, workbook.getSheet("CauHoi").getLastRowNum());
            assertEquals(3, workbook.getSheet("ViDu").getLastRowNum());
            assertTrue(workbook.isSheetHidden(workbook.getSheetIndex("DanhMuc")));
        }
    }

    @Test
    void parsesAllSupportedQuestionTypesAndKeepsLatex() throws Exception {
        QuestionExcelWorkbook excel = new QuestionExcelWorkbook();
        byte[] content = withQuestionRows(excel.template(), List.of(
                List.of("SINGLE_CHOICE", "Giá trị của $E=mc^2$?", "A", "B", "C", "D", "1", "", "Giải thích", 1, "L1"),
                List.of("MULTIPLE_SELECT", "Chọn hai đáp án", "A", "B", "C", "D", "1,3", "", "", 1.5, "L2"),
                List.of("FILL_BLANK", "Điền kết quả", "", "", "", "", "", "một|mot", "", 2, "L3")));

        var questions = excel.parse(content);

        assertEquals(3, questions.size());
        assertEquals(QuestionType.SINGLE_CHOICE, questions.get(0).type());
        assertEquals("Giá trị của $E=mc^2$?", questions.get(0).prompt());
        assertEquals(2, questions.get(1).options().stream().filter(QuizDtos.OptionRequest::correct).count());
        assertEquals(List.of("một", "mot"), questions.get(2).acceptedAnswers());
    }

    @Test
    void reportsEveryInvalidCellInsteadOfOnlyTheFirstFailure() throws Exception {
        QuestionExcelWorkbook excel = new QuestionExcelWorkbook();
        byte[] content = withQuestionRows(excel.template(), List.of(
                List.of("UNKNOWN", "", "", "", "", "", "", "", "", 0, "L9")));

        ApiException error = assertThrows(ApiException.class, () -> excel.parse(content));

        assertEquals("QUESTION_IMPORT_INVALID", error.code());
        assertEquals(List.of("QUESTION_TYPE_INVALID", "QUESTION_PROMPT_REQUIRED", "POINTS_INVALID", "COGNITIVE_LEVEL_INVALID"),
                error.errors().stream().map(item -> item.code()).toList());
    }

    @Test
    void importsOneHundredRowsFromTheTemplate() throws Exception {
        QuestionExcelWorkbook excel = new QuestionExcelWorkbook();
        List<List<Object>> rows = java.util.stream.IntStream.rangeClosed(1, 100)
                .mapToObj(index -> List.<Object>of(
                        "FILL_BLANK", "Câu hỏi " + index, "", "", "", "",
                        "", "Đáp án " + index, "", 1, "L1"))
                .toList();

        var questions = excel.parse(withQuestionRows(excel.template(), rows));

        assertEquals(100, questions.size());
    }

    private static byte[] withQuestionRows(byte[] template, List<List<Object>> values) throws Exception {
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(template));
             var output = new ByteArrayOutputStream()) {
            var sheet = workbook.getSheet("CauHoi");
            for (int rowIndex = 0; rowIndex < values.size(); rowIndex++) {
                var row = sheet.createRow(rowIndex + 1);
                for (int column = 0; column < values.get(rowIndex).size(); column++) {
                    Object value = values.get(rowIndex).get(column);
                    if (value instanceof Number number) row.createCell(column).setCellValue(number.doubleValue());
                    else row.createCell(column).setCellValue(String.valueOf(value));
                }
            }
            workbook.write(output);
            return output.toByteArray();
        }
    }

    private static void assertTrue(boolean value) {
        org.junit.jupiter.api.Assertions.assertTrue(value);
    }
}
