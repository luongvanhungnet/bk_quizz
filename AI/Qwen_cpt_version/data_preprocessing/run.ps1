param(
    [string]$Pdf = '',
    [string]$Manifest = 'D:\bk_quizz_data\slide_processed\_audit\manifest.json',
    [string]$Out = "$PSScriptRoot\outputs\it3170",
    [ValidateSet('native','hybrid','full')][string]$Mode = 'hybrid',
    [string]$Tokenizer = 'Qwen/Qwen2.5-7B',
    [string]$TokenizerRevision = 'main',
    [int]$SequenceLength = 2048
)
$ErrorActionPreference = 'Stop'
if (!$Pdf) {
    $TaskPdfCandidates = @(Get-ChildItem -LiteralPath 'D:\bk_quizz_data\slide_processed\pdf' -Filter 'IT3170-*.pdf' -File)
    if ($TaskPdfCandidates.Count -ne 1) { throw 'Expected exactly one IT3170 PDF. Pass -Pdf explicitly.' }
    $Pdf = $TaskPdfCandidates[0].FullName
}
$TaskPython = "$PSScriptRoot\.venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $TaskPython)) { throw 'Run the environment setup in README.md first.' }
function Invoke-Stage([string[]]$StageArgs) {
    & $TaskPython @StageArgs
    if ($LASTEXITCODE -ne 0) { throw "Pipeline stage failed: $($StageArgs[0])" }
}
Invoke-Stage @("$PSScriptRoot\src\extract.py", '--pdf', $Pdf, '--out', $Out, '--manifest', $Manifest)
if ($Mode -eq 'hybrid') {
    Invoke-Stage @("$PSScriptRoot\src\recognize_components.py", '--out', $Out)
    $TaskFallbackPages = & $TaskPython "$PSScriptRoot\src\select_fallback.py" --out $Out
    if ($LASTEXITCODE -ne 0) { throw 'Failed to select table/scan pages.' }
    if ($TaskFallbackPages) {
        Invoke-Stage @("$PSScriptRoot\src\recognize.py", '--out', $Out, '--pages', $TaskFallbackPages)
    }
}
if ($Mode -eq 'full') { Invoke-Stage @("$PSScriptRoot\src\recognize.py", '--out', $Out, '--pages', 'all') }
if ($Mode -ne 'native') { Invoke-Stage @("$PSScriptRoot\src\check_ocr_charset.py", '--out', $Out) }
$TaskBuildArgs = @("$PSScriptRoot\src\build_dataset.py", '--out', $Out)
if (Test-Path -LiteralPath "$Out\reviewed_annotations.jsonl") {
    $TaskBuildArgs += @('--annotations', "$Out\reviewed_annotations.jsonl")
}
Invoke-Stage $TaskBuildArgs
Invoke-Stage @("$PSScriptRoot\src\pack_qwen.py", '--out', $Out, '--tokenizer', $Tokenizer, '--revision', $TokenizerRevision, '--seq-length', "$SequenceLength")
Invoke-Stage @("$PSScriptRoot\src\validate.py", '--out', $Out)
Invoke-Stage @("$PSScriptRoot\src\make_report.py", '--out', $Out)
