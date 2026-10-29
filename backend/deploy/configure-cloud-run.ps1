[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$ProjectId = "bkquiz-stg-235740",
    [string]$Region = "asia-southeast1",
    [string]$Service = "bkquiz-api",
    [string]$FrontendOrigin = "https://bk-quizz.hung-lv235740.workers.dev",
    [string]$RagServiceUrl = "https://bkquiz-rag-api-990266761128.asia-southeast1.run.app",
    [string]$R2AccountId = "47f7e8f383046c37b06556fc00d0ec2e",
    [string]$R2Bucket = "bkquiz-production",
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$variables = [ordered]@{
    SPRING_PROFILES_ACTIVE        = "prod"
    DATABASE_POOL_SIZE            = "4"
    DATABASE_MIN_IDLE             = "0"
    DATABASE_JDBC_BATCH_SIZE      = "50"
    DATABASE_SLOW_QUERY_MS        = "300"
    FLYWAY_ENABLED                = "false"
    SHUTDOWN_TIMEOUT              = "30s"
    MAX_UPLOAD_SIZE               = "50MB"
    MAX_REQUEST_SIZE              = "55MB"
    API_DOCS_ENABLED              = "false"
    FRONTEND_ORIGINS              = $FrontendOrigin
    COOKIE_SECURE                 = "true"
    JWT_ACCESS_TTL                = "15m"
    REFRESH_TOKEN_TTL             = "7d"
    BCRYPT_STRENGTH               = "12"
    STORAGE_PROVIDER              = "s3"
    LOCAL_STORAGE_ROOT            = "/tmp/bkquiz/uploads"
    LOCAL_STORAGE_TEMP            = "/tmp/bkquiz/tmp"
    USER_STORAGE_QUOTA_BYTES      = "2147483648"
    S3_ENDPOINT                   = "https://$R2AccountId.r2.cloudflarestorage.com"
    S3_REGION                     = "auto"
    S3_BUCKET                     = $R2Bucket
    S3_PATH_STYLE                 = "true"
    CLAMAV_ENABLED                = "false"
    CLAMAV_HOST                   = "localhost"
    CLAMAV_PORT                   = "3310"
    AI_ENABLED                    = "true"
    AI_CHAT_PROVIDER              = "google-genai"
    GEMINI_MODEL                  = "gemini-3.5-flash"
    GEMINI_EMBEDDING_MODEL        = "gemini-embedding-2"
    GEMINI_EMBEDDING_DIMENSIONS   = "768"
    GEMINI_TIMEOUT                = "60s"
    GEMINI_MAX_ATTEMPTS           = "3"
    MAX_QUESTIONS_PER_QUIZ        = "100"
    MAX_SOURCES_PER_GENERATION    = "10"
    MIN_SOURCE_CHARACTERS         = "100"
    QUIZ_BATCH_MAX_QUESTIONS      = "20"
    QUIZ_BATCH_MAX_ATTEMPTS       = "3"
    QUIZ_BATCH_RETRY_DELAY        = "5m"
    QUIZ_BATCH_SUCCESS_DELAY      = "15s"
    WORKER_ENABLED                = "true"
    JOB_POLL_DELAY                = "2s"
    JOB_WORKER_HEARTBEAT_DELAY    = "10s"
    JOB_LEASE_DURATION            = "2m"
    JOB_MAX_ATTEMPTS              = "5"
    RAG_ENABLED                   = "true"
    RAG_SERVICE_URL               = $RagServiceUrl
    RAG_CONNECT_TIMEOUT           = "10s"
    RAG_READ_TIMEOUT              = "900s"
    RAG_HEALTH_POLL_DELAY         = "10s"
    REALTIME_PROVIDER             = "ably"
    ABLY_CHANNEL_PREFIX           = "bkquiz:classroom:"
    ABLY_TOKEN_TTL_SECONDS        = "300"
    REALTIME_PUBLISH_ENABLED      = "true"
    ADMIN_BOOTSTRAP_ENABLED       = "false"
    RESEND_CONNECT_TIMEOUT        = "30s"
    RESEND_READ_TIMEOUT           = "45s"
    RESEND_NETWORK_RETRY_DELAY    = "30s"
    APP_MAIL_FROM                 = "BKQuiz <noreply@luongvanhungnet.xyz>"
}

$secrets = [ordered]@{
    DATABASE_URL                 = "bkquiz-database-url:2"
    DATABASE_USERNAME            = "bkquiz-database-username:latest"
    DATABASE_PASSWORD            = "bkquiz-database-password:latest"
    JWT_ACCESS_SECRET            = "bkquiz-jwt-access-secret:latest"
    S3_ACCESS_KEY                = "bkquiz-r2-access-key:1"
    S3_SECRET_KEY                = "bkquiz-r2-secret-key:1"
    GEMINI_API_KEY               = "GEMINI_API_KEY:latest"
    RAG_INTERNAL_API_KEY         = "bkquiz-rag-internal-key:1"
    RESEND_API_TOKEN             = "bkquiz-resend-api-key:latest"
    ABLY_API_KEY                 = "bkquiz-ably-api-key:latest"
}

if (-not $ValidateOnly -and -not $PSCmdlet.ShouldProcess(
    "$ProjectId/$Region/$Service",
    "Replace all variables and secret references"
)) {
    Write-Host "Will configure $($variables.Count) variables and $($secrets.Count) secrets."
    return
}

$currentServiceJson = gcloud run services describe $Service `
    --project=$ProjectId `
    --region=$Region `
    --format=json | ConvertFrom-Json
$currentEnvironment = @($currentServiceJson.spec.template.spec.containers[0].env)

# RESEND_API_URL is intentionally unmanaged. Preserve its current Cloud Run
# binding so the bulk --set operation does not delete or change its type.
$currentResendApiUrl = @($currentEnvironment | Where-Object name -eq "RESEND_API_URL") | Select-Object -Last 1
if ($null -ne $currentResendApiUrl) {
    if ($currentResendApiUrl.valueFrom) {
        $secretReference = $currentResendApiUrl.valueFrom.secretKeyRef
        $secrets["RESEND_API_URL"] = "$($secretReference.name):$($secretReference.key)"
    }
    else {
        $variables["RESEND_API_URL"] = [string]$currentResendApiUrl.value
    }
}

foreach ($reference in $secrets.Values) {
    $parts = $reference -split ":", 2
    gcloud secrets versions describe $($parts[1]) `
        --secret=$($parts[0]) `
        --project=$ProjectId `
        --format="value(name)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Secret or version does not exist: $reference"
    }
}

$envArgument = ($variables.GetEnumerator() | ForEach-Object {
    "$($_.Key)=$($_.Value)"
}) -join ","
$secretArgument = ($secrets.GetEnumerator() | ForEach-Object {
    "$($_.Key)=$($_.Value)"
}) -join ","

$currentSecretNames = @($currentEnvironment | Where-Object valueFrom | ForEach-Object name)
$currentLiteralNames = @($currentEnvironment | Where-Object { -not $_.valueFrom } | ForEach-Object name)
$secretToLiteral = @($variables.Keys | Where-Object { $_ -in $currentSecretNames })
$literalToSecret = @($secrets.Keys | Where-Object { $_ -in $currentLiteralNames })

if ($ValidateOnly) {
    Write-Host "Validated $($secrets.Count) secret references."
    Write-Host "Ready to configure $($variables.Count) variables."
    if ($secretToLiteral.Count -gt 0) {
        Write-Host "Will convert from secret to literal: $($secretToLiteral -join ', ')"
    }
    if ($literalToSecret.Count -gt 0) {
        Write-Host "Will convert from literal to secret: $($literalToSecret -join ', ')"
    }
    return
}

if ($secretToLiteral.Count -gt 0 -or $literalToSecret.Count -gt 0) {
    $normalizationArguments = @(
        "run", "services", "update", $Service,
        "--project=$ProjectId",
        "--region=$Region"
    )

    if ($secretToLiteral.Count -gt 0) {
        $literalUpdates = ($secretToLiteral | ForEach-Object {
            "$_=$($variables[$_])"
        }) -join ","
        $normalizationArguments += "--remove-secrets=$($secretToLiteral -join ',')"
        $normalizationArguments += "--update-env-vars=$literalUpdates"
    }

    if ($literalToSecret.Count -gt 0) {
        $secretUpdates = ($literalToSecret | ForEach-Object {
            "$_=$($secrets[$_])"
        }) -join ","
        $normalizationArguments += "--remove-env-vars=$($literalToSecret -join ',')"
        $normalizationArguments += "--update-secrets=$secretUpdates"
    }

    Write-Host "Normalizing Cloud Run environment variable types."
    & gcloud @normalizationArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to normalize Cloud Run environment variable types for $Service."
    }
}

gcloud run services update $Service `
    --project=$ProjectId `
    --region=$Region `
    "--set-env-vars=$envArgument" `
    "--set-secrets=$secretArgument"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to update Cloud Run service $Service."
}

$serviceJson = gcloud run services describe $Service `
    --project=$ProjectId `
    --region=$Region `
    --format=json | ConvertFrom-Json
$container = $serviceJson.spec.template.spec.containers[0]
$duplicates = @($container.env | Group-Object name | Where-Object Count -gt 1)
if ($duplicates.Count -gt 0) {
    throw "Duplicate Cloud Run environment variables remain: $($duplicates.Name -join ', ')"
}

$configuredNames = @($container.env | ForEach-Object name | Sort-Object)
Write-Host "Updated $($variables.Count) variables and $($secrets.Count) secrets."
Write-Host "No duplicate environment variable names remain."
Write-Host "Revision: $($serviceJson.status.latestCreatedRevisionName)"
Write-Host "URL: $($serviceJson.status.url)"
Write-Host "Configuration names: $($configuredNames -join ', ')"
