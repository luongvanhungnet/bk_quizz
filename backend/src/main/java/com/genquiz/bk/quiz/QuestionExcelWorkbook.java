package com.genquiz.bk.quiz;

import com.genquiz.bk.common.api.ApiFieldError;
import com.genquiz.bk.common.error.ApiException;
import java.io.ByteArrayOutputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Locale;
import java.util.List;
import java.util.Set;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.DataValidation;
import org.apache.poi.ss.usermodel.DataValidationConstraint;
import org.apache.poi.ss.usermodel.FillPatternType;
import org.apache.poi.ss.usermodel.Font;
import org.apache.poi.ss.usermodel.HorizontalAlignment;
import org.apache.poi.ss.usermodel.IndexedColors;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.VerticalAlignment;
import org.apache.poi.ss.util.CellRangeAddressList;
import org.apache.poi.xssf.usermodel.XSSFDataValidationHelper;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class QuestionExcelWorkbook {
    private static final int MAX_ERRORS = 200;
    static final String IMPORT_SHEET = "CauHoi";
    static final List<String> HEADERS = List.of(
            "Loại câu hỏi", "Nội dung", "Lựa chọn 1", "Lựa chọn 2",
            "Lựa chọn 3", "Lựa chọn 4", "Đáp án đúng", "Đáp án chấp nhận",
            "Giải thích", "Điểm", "Mức độ tư duy");

    byte[] template() {
        try (var workbook = new XSSFWorkbook();
             var output = new ByteArrayOutputStream()) {
            CellStyle title = titleStyle(workbook);
            CellStyle header = headerStyle(workbook);
            CellStyle wrapped = wrappedStyle(workbook);

            Sheet guide = workbook.createSheet("HuongDan");
            buildGuide(guide, title, header, wrapped);

            Sheet importSheet = workbook.createSheet(IMPORT_SHEET);
            buildQuestionSheet(importSheet, header, wrapped, List.of());

            Sheet examples = workbook.createSheet("ViDu");
            buildQuestionSheet(examples, header, wrapped, exampleRows());

            Sheet catalog = workbook.createSheet("DanhMuc");
            buildCatalog(workbook, catalog);
            addDropdowns(importSheet);
            workbook.setSheetHidden(workbook.getSheetIndex(catalog), true);

            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new IllegalStateException("Không thể tạo file Excel mẫu.", exception);
        }
    }

    List<QuizDtos.QuestionRequest> parse(byte[] content) {
        return parseRows(content).stream().map(ParsedQuestion::question).toList();
    }

    List<ParsedQuestion> parseRows(byte[] content) {
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(content))) {
            Sheet sheet = workbook.getSheet(IMPORT_SHEET);
            if (sheet == null) {
                throw invalid(List.of(error("IMPORT_SHEET_MISSING", IMPORT_SHEET,
                        "Không tìm thấy sheet CauHoi.")));
            }
            ErrorCollector errors = new ErrorCollector();
            validateHeaders(sheet, errors);
            if (errors.hasErrors()) throw invalid(errors.values());

            DataFormatter formatter = new DataFormatter(Locale.ROOT);
            List<ParsedQuestion> result = new ArrayList<>();
            Set<String> prompts = new HashSet<>();
            int nonBlankRows = 0;
            for (int rowIndex = 1; rowIndex <= sheet.getLastRowNum(); rowIndex++) {
                Row row = sheet.getRow(rowIndex);
                if (isBlank(row, formatter)) continue;
                nonBlankRows++;
                if (nonBlankRows > QuizLimits.MAX_QUESTIONS_PER_QUIZ) {
                    errors.add(error("QUIZ_QUESTION_LIMIT_EXCEEDED", cell(rowIndex, 0),
                            "Hàng " + (rowIndex + 1)
                                    + ": Một file chỉ được chứa tối đa "
                                    + QuizLimits.MAX_QUESTIONS_PER_QUIZ
                                    + " câu hỏi."));
                    break;
                }
                QuizDtos.QuestionRequest request = parseRow(row, rowIndex, formatter, errors);
                if (request != null) {
                    String prompt = normalize(request.prompt());
                    if (!prompts.add(prompt)) {
                        errors.add(error("DUPLICATE_QUESTION", cell(rowIndex, 1),
                                "Hàng " + (rowIndex + 1) + " – Nội dung: Câu hỏi bị trùng trong file Excel."));
                    } else {
                        result.add(new ParsedQuestion(rowIndex + 1, request));
                    }
                }
            }
            if (nonBlankRows == 0) {
                errors.add(error("QUESTION_IMPORT_EMPTY", IMPORT_SHEET,
                        "Sheet CauHoi chưa có câu hỏi nào."));
            }
            if (errors.hasErrors()) throw invalid(errors.values());
            return List.copyOf(result);
        } catch (ApiException exception) {
            throw exception;
        } catch (Exception exception) {
            throw invalid(List.of(error("EXCEL_FILE_INVALID", "file",
                    "File không phải workbook .xlsx hợp lệ hoặc đã bị hỏng.")));
        }
    }

    record ParsedQuestion(int excelRowNumber, QuizDtos.QuestionRequest question) {}

    private static QuizDtos.QuestionRequest parseRow(Row row, int rowIndex, DataFormatter formatter,
                                                      ErrorCollector errors) {
        int before = errors.size();
        rejectFormulaCells(row, rowIndex, errors);
        String typeText = text(row, 0, formatter);
        QuestionType type = enumValue(QuestionType.class, typeText);
        if (type == null) {
            errors.add(error("QUESTION_TYPE_INVALID", cell(rowIndex, 0),
                    "Hàng " + (rowIndex + 1) + " – Loại câu hỏi: Chỉ chấp nhận SINGLE_CHOICE, MULTIPLE_SELECT hoặc FILL_BLANK."));
        }
        String prompt = text(row, 1, formatter);
        if (prompt.isBlank()) {
            errors.add(error("QUESTION_PROMPT_REQUIRED", cell(rowIndex, 1),
                    "Hàng " + (rowIndex + 1) + " – Nội dung: Không được để trống."));
        }
        String explanation = nullable(text(row, 8, formatter));
        BigDecimal points = parsePoints(row, rowIndex, formatter, errors);
        String levelText = text(row, 10, formatter);
        CognitiveLevel level = enumValue(CognitiveLevel.class, levelText);
        if (level == null) {
            errors.add(error("COGNITIVE_LEVEL_INVALID", cell(rowIndex, 10),
                    "Hàng " + (rowIndex + 1) + " – Mức độ tư duy: Chỉ chấp nhận L1, L2, L3, L4 hoặc L5."));
        }

        List<QuizDtos.OptionRequest> options = List.of();
        List<String> acceptedAnswers = List.of();
        if (type == QuestionType.FILL_BLANK) {
            for (int column = 2; column <= 5; column++) {
                if (!text(row, column, formatter).isBlank()) {
                    errors.add(error("OPTION_NOT_ALLOWED", cell(rowIndex, column),
                            "Hàng " + (rowIndex + 1) + ": Câu FILL_BLANK không được có lựa chọn."));
                }
            }
            if (!text(row, 6, formatter).isBlank()) {
                errors.add(error("CORRECT_ANSWER_INVALID", cell(rowIndex, 6),
                        "Hàng " + (rowIndex + 1) + " – Đáp án đúng: Hãy để trống với FILL_BLANK."));
            }
            acceptedAnswers = splitAcceptedAnswers(text(row, 7, formatter));
            if (acceptedAnswers.isEmpty()) {
                errors.add(error("ACCEPTED_ANSWER_REQUIRED", cell(rowIndex, 7),
                        "Hàng " + (rowIndex + 1) + " – Đáp án chấp nhận: Phải có ít nhất một đáp án."));
            }
        } else if (type != null) {
            List<String> optionTexts = new ArrayList<>();
            Set<String> distinct = new HashSet<>();
            for (int column = 2; column <= 5; column++) {
                String value = text(row, column, formatter);
                optionTexts.add(value);
                if (value.isBlank()) {
                    errors.add(error("OPTION_REQUIRED", cell(rowIndex, column),
                            "Hàng " + (rowIndex + 1) + " – Lựa chọn " + (column - 1) + ": Không được để trống."));
                } else if (!distinct.add(normalize(value))) {
                    errors.add(error("OPTION_DUPLICATE", cell(rowIndex, column),
                            "Hàng " + (rowIndex + 1) + ": Các lựa chọn không được trùng nhau."));
                }
            }
            Set<Integer> correct = parseCorrectAnswers(text(row, 6, formatter), rowIndex, type, errors);
            List<QuizDtos.OptionRequest> optionValues = new ArrayList<>();
            for (int index = 0; index < optionTexts.size(); index++) {
                optionValues.add(new QuizDtos.OptionRequest(optionTexts.get(index), correct.contains(index + 1)));
            }
            options = List.copyOf(optionValues);
            if (!text(row, 7, formatter).isBlank()) {
                errors.add(error("ACCEPTED_ANSWER_NOT_ALLOWED", cell(rowIndex, 7),
                        "Hàng " + (rowIndex + 1) + " – Đáp án chấp nhận: Chỉ dùng cho FILL_BLANK."));
            }
        }
        if (errors.size() > before || type == null || points == null || level == null) return null;
        var request = new QuizDtos.QuestionRequest(type, prompt, explanation, points, null, level,
                null, null, options, acceptedAnswers);
        try {
            QuestionService.validate(request);
            return request;
        } catch (ResponseStatusException exception) {
            errors.add(error("QUESTION_ROW_INVALID", "CauHoi!" + (rowIndex + 1),
                    "Hàng " + (rowIndex + 1) + ": " + exception.getReason()));
            return null;
        }
    }

    private static void validateHeaders(Sheet sheet, ErrorCollector errors) {
        Row row = sheet.getRow(0);
        for (int column = 0; column < HEADERS.size(); column++) {
            String actual = row == null ? "" : new DataFormatter(Locale.ROOT).formatCellValue(row.getCell(column)).trim();
            if (!HEADERS.get(column).equals(actual)) {
                errors.add(error("IMPORT_HEADER_INVALID", cell(0, column),
                        "Ô " + cell(0, column) + " phải có tiêu đề “" + HEADERS.get(column) + "”."));
            }
        }
    }

    private static void rejectFormulaCells(Row row, int rowIndex, ErrorCollector errors) {
        for (int column = 0; column < HEADERS.size(); column++) {
            Cell value = row.getCell(column);
            if (value != null && value.getCellType() == CellType.FORMULA) {
                errors.add(error("EXCEL_FORMULA_NOT_ALLOWED", cell(rowIndex, column),
                        "Ô " + cell(rowIndex, column) + " chứa công thức. Hãy nhập giá trị tĩnh."));
            }
        }
    }

    private static BigDecimal parsePoints(Row row, int rowIndex, DataFormatter formatter,
                                          ErrorCollector errors) {
        Cell value = row.getCell(9);
        try {
            BigDecimal points = value != null && value.getCellType() == CellType.NUMERIC
                    ? BigDecimal.valueOf(value.getNumericCellValue())
                    : new BigDecimal(text(row, 9, formatter).replace(',', '.'));
            points = points.stripTrailingZeros();
            if (points.signum() <= 0 || points.scale() > 2 || points.precision() - Math.max(points.scale(), 0) > 6) {
                throw new NumberFormatException();
            }
            return points;
        } catch (RuntimeException exception) {
            errors.add(error("POINTS_INVALID", cell(rowIndex, 9),
                    "Hàng " + (rowIndex + 1) + " – Điểm: Phải là số dương, tối đa 999999.99 và có không quá 2 chữ số thập phân."));
            return null;
        }
    }

    private static Set<Integer> parseCorrectAnswers(String value, int rowIndex, QuestionType type,
                                                    ErrorCollector errors) {
        Set<Integer> result = new java.util.LinkedHashSet<>();
        try {
            if (!value.isBlank()) {
                for (String item : value.split(",")) {
                    int index = Integer.parseInt(item.trim());
                    if (index < 1 || index > 4 || !result.add(index)) throw new NumberFormatException();
                }
            }
            boolean valid = type == QuestionType.SINGLE_CHOICE ? result.size() == 1 : result.size() >= 2;
            if (!valid) throw new NumberFormatException();
        } catch (NumberFormatException exception) {
            errors.add(error("CORRECT_ANSWER_INVALID", cell(rowIndex, 6),
                    "Hàng " + (rowIndex + 1) + " – Đáp án đúng: "
                            + (type == QuestionType.SINGLE_CHOICE
                            ? "Nhập đúng một số từ 1 đến 4."
                            : "Nhập ít nhất hai số khác nhau từ 1 đến 4, cách nhau bằng dấu phẩy.")));
            result.clear();
        }
        return result;
    }

    private static List<String> splitAcceptedAnswers(String value) {
        if (value.isBlank()) return List.of();
        return java.util.Arrays.stream(value.split("\\|", -1)).map(String::trim)
                .filter(item -> !item.isBlank()).toList();
    }

    private static boolean isBlank(Row row, DataFormatter formatter) {
        if (row == null) return true;
        for (int column = 0; column < HEADERS.size(); column++) {
            if (!text(row, column, formatter).isBlank()) return false;
        }
        return true;
    }

    private static String text(Row row, int column, DataFormatter formatter) {
        if (row == null || row.getCell(column) == null) return "";
        return formatter.formatCellValue(row.getCell(column)).trim();
    }

    private static <T extends Enum<T>> T enumValue(Class<T> type, String value) {
        try {
            return Enum.valueOf(type, value.trim().toUpperCase(Locale.ROOT));
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private static String normalize(String value) {
        return Normalizer.normalize(value == null ? "" : value, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT).replaceAll("\\s+", " ").trim();
    }

    private static String nullable(String value) {
        return value.isBlank() ? null : value;
    }

    private static String cell(int zeroBasedRow, int zeroBasedColumn) {
        return IMPORT_SHEET + "!" + org.apache.poi.ss.util.CellReference.convertNumToColString(zeroBasedColumn)
                + (zeroBasedRow + 1);
    }

    private static ApiFieldError error(String code, String field, String message) {
        return new ApiFieldError(code, field, message);
    }

    private static ApiException invalid(List<ApiFieldError> errors) {
        return new ApiException(HttpStatus.UNPROCESSABLE_CONTENT, "QUESTION_IMPORT_INVALID",
                "File Excel có dữ liệu không hợp lệ.", errors);
    }

    private static final class ErrorCollector {
        private final List<ApiFieldError> errors = new ArrayList<>();
        private int omitted;

        void add(ApiFieldError error) {
            if (errors.size() < MAX_ERRORS) errors.add(error);
            else omitted++;
        }

        int size() { return errors.size() + omitted; }
        boolean hasErrors() { return size() > 0; }

        List<ApiFieldError> values() {
            List<ApiFieldError> result = new ArrayList<>(errors);
            if (omitted > 0) result.add(new ApiFieldError("IMPORT_ERRORS_TRUNCATED", null,
                    "Còn " + omitted + " lỗi khác chưa hiển thị."));
            return List.copyOf(result);
        }
    }

    private static void buildGuide(Sheet sheet, CellStyle title, CellStyle header, CellStyle wrapped) {
        Row titleRow = sheet.createRow(0);
        titleRow.createCell(0).setCellValue("HƯỚNG DẪN IMPORT CÂU HỎI BKQUIZ");
        titleRow.getCell(0).setCellStyle(title);
        sheet.addMergedRegion(new org.apache.poi.ss.util.CellRangeAddress(0, 0, 0, 2));

        String[][] values = {
                {"Mục", "Quy tắc", "Ví dụ"},
                {"Sheet nhập", "Chỉ nhập dữ liệu trong sheet CauHoi. Không đổi tên hoặc xóa cột.", ""},
                {"Loại câu hỏi", "SINGLE_CHOICE, MULTIPLE_SELECT hoặc FILL_BLANK", "SINGLE_CHOICE"},
                {"Đáp án đúng", "Số thứ tự 1-4; nhiều đáp án cách nhau bằng dấu phẩy", "1,3"},
                {"Đáp án chấp nhận", "Chỉ dùng cho FILL_BLANK; cách nhau bằng dấu |", "Hà Nội|Ha Noi"},
                {"Điểm", "Số dương, tối đa 2 chữ số thập phân", "1.5"},
                {"Mức độ tư duy", "L1, L2, L3, L4 hoặc L5", "L3"},
                {"Công thức", "Hỗ trợ Markdown/LaTeX; giữ nguyên dấu gạch chéo", "$E=mc^2$"},
                {"Giới hạn", "File .xlsx tối đa 5 MB; tổng Quiz tối đa "
                        + QuizLimits.MAX_QUESTIONS_PER_QUIZ + " câu", ""},
                {"Lưu ý", "Nếu một dòng sai, hệ thống không nhập bất kỳ dòng nào.", ""},
        };
        for (int rowIndex = 0; rowIndex < values.length; rowIndex++) {
            Row row = sheet.createRow(rowIndex + 2);
            for (int column = 0; column < values[rowIndex].length; column++) {
                row.createCell(column).setCellValue(values[rowIndex][column]);
                row.getCell(column).setCellStyle(rowIndex == 0 ? header : wrapped);
            }
        }
        sheet.setColumnWidth(0, 22 * 256);
        sheet.setColumnWidth(1, 68 * 256);
        sheet.setColumnWidth(2, 28 * 256);
        sheet.createFreezePane(0, 3);
    }

    private static void buildQuestionSheet(Sheet sheet, CellStyle header, CellStyle wrapped,
                                           List<List<Object>> rows) {
        Row headerRow = sheet.createRow(0);
        for (int column = 0; column < HEADERS.size(); column++) {
            headerRow.createCell(column).setCellValue(HEADERS.get(column));
            headerRow.getCell(column).setCellStyle(header);
        }
        for (int rowIndex = 0; rowIndex < rows.size(); rowIndex++) {
            Row row = sheet.createRow(rowIndex + 1);
            List<Object> values = rows.get(rowIndex);
            for (int column = 0; column < values.size(); column++) {
                Object value = values.get(column);
                if (value instanceof Number number) row.createCell(column).setCellValue(number.doubleValue());
                else row.createCell(column).setCellValue(String.valueOf(value));
                row.getCell(column).setCellStyle(wrapped);
            }
        }
        int[] widths = {22, 48, 25, 25, 25, 25, 18, 28, 42, 12, 20};
        for (int index = 0; index < widths.length; index++) sheet.setColumnWidth(index, widths[index] * 256);
        sheet.createFreezePane(0, 1);
        sheet.setAutoFilter(new org.apache.poi.ss.util.CellRangeAddress(0, Math.max(1, rows.size()), 0, HEADERS.size() - 1));
    }

    private static List<List<Object>> exampleRows() {
        return List.of(
                List.of("SINGLE_CHOICE", "Thủ đô của Việt Nam là gì?", "Hà Nội", "Huế", "Đà Nẵng", "TP.HCM", "1", "", "Hà Nội là thủ đô của Việt Nam.", 1, "L1"),
                List.of("MULTIPLE_SELECT", "Chọn các số nguyên tố.", "2", "3", "4", "6", "1,2", "", "2 và 3 là số nguyên tố.", 1.5, "L2"),
                List.of("FILL_BLANK", "Công thức năng lượng nổi tiếng là ____.", "", "", "", "", "", "$E=mc^2$|E=mc^2", "Công thức tương đối tính của Einstein.", 2, "L3"));
    }

    private static void buildCatalog(XSSFWorkbook workbook, Sheet sheet) {
        String[] types = {"SINGLE_CHOICE", "MULTIPLE_SELECT", "FILL_BLANK"};
        for (int index = 0; index < types.length; index++) sheet.createRow(index).createCell(0).setCellValue(types[index]);
        String[] levels = {"L1", "L2", "L3", "L4", "L5"};
        for (int index = 0; index < levels.length; index++) {
            Row row = sheet.getRow(index);
            if (row == null) row = sheet.createRow(index);
            row.createCell(1).setCellValue(levels[index]);
        }
        var typeName = workbook.createName();
        typeName.setNameName("QuestionTypes");
        typeName.setRefersToFormula("'DanhMuc'!$A$1:$A$3");
        var levelName = workbook.createName();
        levelName.setNameName("CognitiveLevels");
        levelName.setRefersToFormula("'DanhMuc'!$B$1:$B$5");
    }

    private static void addDropdowns(Sheet sheet) {
        var helper = new XSSFDataValidationHelper((org.apache.poi.xssf.usermodel.XSSFSheet) sheet);
        addDropdown(sheet, helper, 0, "QuestionTypes");
        addDropdown(sheet, helper, 10, "CognitiveLevels");
    }

    private static void addDropdown(Sheet sheet, XSSFDataValidationHelper helper,
                                    int column, String formula) {
        DataValidationConstraint constraint = helper.createFormulaListConstraint(formula);
        DataValidation validation = helper.createValidation(
                constraint, new CellRangeAddressList(
                        1, QuizLimits.MAX_QUESTIONS_PER_QUIZ, column, column));
        validation.setShowErrorBox(true);
        validation.createErrorBox("Giá trị không hợp lệ", "Hãy chọn một giá trị trong danh sách.");
        sheet.addValidationData(validation);
    }

    private static CellStyle titleStyle(XSSFWorkbook workbook) {
        CellStyle style = workbook.createCellStyle();
        Font font = workbook.createFont();
        font.setBold(true);
        font.setFontHeightInPoints((short) 16);
        font.setColor(IndexedColors.WHITE.getIndex());
        style.setFont(font);
        style.setFillForegroundColor(IndexedColors.DARK_BLUE.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        style.setAlignment(HorizontalAlignment.CENTER);
        style.setVerticalAlignment(VerticalAlignment.CENTER);
        return style;
    }

    private static CellStyle headerStyle(XSSFWorkbook workbook) {
        CellStyle style = workbook.createCellStyle();
        Font font = workbook.createFont();
        font.setBold(true);
        font.setColor(IndexedColors.WHITE.getIndex());
        style.setFont(font);
        style.setFillForegroundColor(IndexedColors.DARK_RED.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        style.setWrapText(true);
        style.setVerticalAlignment(VerticalAlignment.CENTER);
        return style;
    }

    private static CellStyle wrappedStyle(XSSFWorkbook workbook) {
        CellStyle style = workbook.createCellStyle();
        style.setWrapText(true);
        style.setVerticalAlignment(VerticalAlignment.TOP);
        return style;
    }
}
