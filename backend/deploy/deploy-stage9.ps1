[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [string]$ProjectId = "bkquiz-stg-235740",
    [string]$Region = "asia-southeast1",
    [string]$BackendService = "bkquiz-api",
    [string]$RagService = "bkquiz-rag-api",
    [string]$BackendServiceAccount = "",
    [Parameter(Mandatory = $true)]
    [string]$BackendImage,
    [string[]]$NotificationChannels = @(),
    [switch]$SkipMonitoring,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

function Invoke-Gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & gcloud @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        throw "gcloud command failed: gcloud $($Arguments -join ' ')"
    }
}

function Test-GcloudResource {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & gcloud @Arguments *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Get-Service {
    param([string]$Name)
    return Invoke-Gcloud run services describe $Name `
        --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json
}

function Assert-SecretBindings {
    param(
        [object]$Service,
        [string[]]$Names,
        [string]$ServiceName
    )
    $environment = @($Service.spec.template.spec.containers[0].env)
    foreach ($name in $Names) {
        $binding = @($environment | Where-Object name -eq $name) | Select-Object -Last 1
        if ($null -ne $binding -and -not $binding.valueFrom) {
            throw "$ServiceName has sensitive variable $name configured as a literal. Move it to Secret Manager first."
        }
    }
}

function Remove-OllamaConfiguration {
    param([object]$Service)
    $ollamaNames = @(
        "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_TIMEOUT_SECONDS",
        "OLLAMA_CONTEXT_SIZE", "OLLAMA_MAX_OUTPUT_TOKENS",
        "OLLAMA_TEMPERATURE", "OLLAMA_KEEP_ALIVE",
        "OLLAMA_MAX_QUESTIONS_PER_CALL", "OLLAMA_BATCH_MAX_RETRIES"
    )
    $environment = @($Service.spec.template.spec.containers[0].env)
    $literalNames = @()
    $secretNames = @()
    foreach ($name in $ollamaNames) {
        $binding = @($environment | Where-Object name -eq $name) | Select-Object -Last 1
        if ($null -eq $binding) { continue }
        if ($binding.valueFrom) { $secretNames += $name }
        else { $literalNames += $name }
    }
    $arguments = @(
        "run", "services", "update", $RagService,
        "--project=$ProjectId", "--region=$Region",
        "--invoker-iam-check",
        "--update-env-vars=OLLAMA_ENABLED=false"
    )
    if ($literalNames.Count -gt 0) {
        $arguments += "--remove-env-vars=$($literalNames -join ',')"
    }
    if ($secretNames.Count -gt 0) {
        $arguments += "--remove-secrets=$($secretNames -join ',')"
    }
    Invoke-Gcloud @arguments
}

function Ensure-ErrorAlert {
    param([string]$ServiceName)
    $displayName = "BKQuiz $ServiceName Cloud Run 5xx"
    $existing = Invoke-Gcloud monitoring policies list `
        --project=$ProjectId `
        "--filter=displayName=`"$displayName`"" `
        --format="value(name)"
    if (-not [string]::IsNullOrWhiteSpace([string]$existing)) {
        Write-Host "Alert policy already exists: $displayName"
        return
    }

    $policy = [ordered]@{
        displayName = $displayName
        combiner = "OR"
        enabled = $true
        documentation = [ordered]@{
            mimeType = "text/markdown"
            content = "Cloud Run service $ServiceName has continuously returned 5xx responses for five minutes. Check the active revision and application logs before retrying jobs."
        }
        conditions = @([ordered]@{
            displayName = "$ServiceName 5xx rate"
            conditionThreshold = [ordered]@{
                filter = "resource.type = `"cloud_run_revision`" AND resource.labels.service_name = `"$ServiceName`" AND metric.type = `"run.googleapis.com/request_count`" AND metric.labels.response_code_class = `"5xx`""
                aggregations = @([ordered]@{
                    alignmentPeriod = "60s"
                    perSeriesAligner = "ALIGN_RATE"
                    crossSeriesReducer = "REDUCE_SUM"
                    groupByFields = @("resource.label.service_name")
                })
                comparison = "COMPARISON_GT"
                thresholdValue = 0.01
                duration = "300s"
                trigger = @{ count = 1 }
            }
        })
        notificationChannels = @($NotificationChannels)
        userLabels = @{ application = "bkquiz"; stage = "9" }
    }
    $temporary = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText(
            $temporary,
            ($policy | ConvertTo-Json -Depth 12),
            [Text.UTF8Encoding]::new($false)
        )
        Invoke-Gcloud monitoring policies create `
            --project=$ProjectId --policy-from-file=$temporary
    }
    finally {
        Remove-Item $temporary -Force -ErrorAction SilentlyContinue
    }
}

Invoke-Gcloud artifacts docker images describe $BackendImage `
    --project=$ProjectId --format="value(image_summary.digest)" | Out-Null
$backend = Get-Service $BackendService
$rag = Get-Service $RagService
$ragUrl = ([string]$rag.status.url).TrimEnd("/")
if ([string]::IsNullOrWhiteSpace($ragUrl) -or -not $ragUrl.StartsWith("https://")) {
    throw "Unable to resolve the HTTPS URL for $RagService."
}

if (-not $BackendServiceAccount) {
    $BackendServiceAccount = [string]$backend.spec.template.spec.serviceAccountName
}
if ([string]::IsNullOrWhiteSpace($BackendServiceAccount)) {
    throw "Cloud Run backend does not have a runtime service account."
}
if (-not (Test-GcloudResource iam service-accounts describe `
    $BackendServiceAccount --project=$ProjectId)) {
    throw "Backend runtime service account does not exist: $BackendServiceAccount"
}

Assert-SecretBindings $backend @(
    "DATABASE_PASSWORD", "JWT_ACCESS_SECRET", "S3_ACCESS_KEY", "S3_SECRET_KEY",
    "RAG_INTERNAL_API_KEY", "GEMINI_API_KEY", "RESEND_API_TOKEN", "RESEND_API_KEY", "ABLY_API_KEY"
) $BackendService
Assert-SecretBindings $rag @(
    "DATABASE_URL", "SPRING_BOOT_INTERNAL_API_KEY", "GEMINI_API_KEY",
    "QDRANT_API_KEY", "DOCUMENT_STORAGE_ACCESS_KEY",
    "DOCUMENT_STORAGE_SECRET_KEY", "CACHE_REDIS_URL"
) $RagService

if ($ValidateOnly) {
    Write-Host "Stage 9 preflight passed."
    Write-Host "Backend service account: $BackendServiceAccount"
    Write-Host "RAG IAM audience: $ragUrl"
    Write-Host "No secret values were read or printed."
    return
}

if (-not $PSCmdlet.ShouldProcess(
    "$ProjectId/$Region/$BackendService -> $RagService",
    "Deploy Stage 9 IAM and production hardening"
)) {
    Write-Host "Would deploy the backend image, enable RAG IAM, disable Ollama, remove public RAG access, and configure alerts."
    return
}

Invoke-Gcloud services enable `
    run.googleapis.com iamcredentials.googleapis.com `
    monitoring.googleapis.com logging.googleapis.com `
    --project=$ProjectId

Invoke-Gcloud run services add-iam-policy-binding $RagService `
    --project=$ProjectId --region=$Region `
    --member="serviceAccount:$BackendServiceAccount" `
    --role="roles/run.invoker"

Invoke-Gcloud run services update $BackendService `
    --project=$ProjectId --region=$Region `
    --image=$BackendImage `
    "--update-env-vars=RAG_IAM_ENABLED=true,RAG_IAM_AUDIENCE=$ragUrl"

Remove-OllamaConfiguration $rag

$policy = Invoke-Gcloud run services get-iam-policy $RagService `
    --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json
$publicInvoker = @($policy.bindings | Where-Object role -eq "roles/run.invoker" | ForEach-Object members) `
    -contains "allUsers"
if ($publicInvoker) {
    Invoke-Gcloud run services remove-iam-policy-binding $RagService `
        --project=$ProjectId --region=$Region `
        --member="allUsers" --role="roles/run.invoker"
}
$authenticatedInvoker = @($policy.bindings | Where-Object role -eq "roles/run.invoker" | ForEach-Object members) `
    -contains "allAuthenticatedUsers"
if ($authenticatedInvoker) {
    Invoke-Gcloud run services remove-iam-policy-binding $RagService `
        --project=$ProjectId --region=$Region `
        --member="allAuthenticatedUsers" --role="roles/run.invoker"
}

if (-not $SkipMonitoring) {
    Ensure-ErrorAlert $BackendService
    Ensure-ErrorAlert $RagService
}

$updatedBackend = Get-Service $BackendService
$updatedRag = Get-Service $RagService
$backendEnvironment = @($updatedBackend.spec.template.spec.containers[0].env)
$ragEnvironment = @($updatedRag.spec.template.spec.containers[0].env)
$iamEnabled = @($backendEnvironment | Where-Object name -eq "RAG_IAM_ENABLED") | Select-Object -Last 1
$ollamaEnabled = @($ragEnvironment | Where-Object name -eq "OLLAMA_ENABLED") | Select-Object -Last 1
if ($iamEnabled.value -ne "true") {
    throw "RAG_IAM_ENABLED was not enabled on $BackendService."
}
if ($ollamaEnabled.value -ne "false") {
    throw "OLLAMA_ENABLED was not disabled on $RagService."
}
$updatedPolicy = Invoke-Gcloud run services get-iam-policy $RagService `
    --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json
$stillPublic = @($updatedPolicy.bindings | Where-Object role -eq "roles/run.invoker" | ForEach-Object members) `
    | Where-Object { $_ -in @("allUsers", "allAuthenticatedUsers") }
if (@($stillPublic).Count -gt 0) {
    throw "$RagService is still publicly invokable."
}

Write-Host "Stage 9 deployment completed."
Write-Host "Backend revision: $($updatedBackend.status.latestCreatedRevisionName)"
Write-Host "RAG revision: $($updatedRag.status.latestCreatedRevisionName)"
Write-Host "RAG is private and Spring authenticates with a Cloud Run ID token."
Write-Host "Ollama is disabled and its production configuration was removed."
