import { validateQuestionImportFile } from "./questionImport";

describe("validateQuestionImportFile", () => {
  it("accepts only xlsx files no larger than five megabytes", () => {
    expect(validateQuestionImportFile(new File(["ok"], "questions.xlsx"))).toBeNull();
    expect(validateQuestionImportFile(new File(["legacy"], "questions.xls"))).toContain(".xlsx");
    expect(validateQuestionImportFile(new File(["macro"], "questions.xlsm"))).toContain(".xlsx");
    expect(validateQuestionImportFile(new File([new Uint8Array(5 * 1024 * 1024 + 1)], "large.xlsx")))
      .toContain("5 MB");
  });
});
