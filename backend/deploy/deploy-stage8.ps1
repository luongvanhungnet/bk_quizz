[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$ProjectId = "bkquiz-stg-235740",
    [string]$Region = "asia-southeast1",
    [string]$Service = "bkquiz-api",
    [string]$AblySecret = "bkquiz-ably-api-key",
    [string]$AblySecretVersion = "latest",
    [string]$ChannelPrefix = "bkquiz:classroom:",
    [int]$TokenTtlSeconds = 300,
    [Parameter(Mandatory = $true)]
    [string]$Image,
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

if ($TokenTtlSeconds -lt 60 -or $TokenTtlSeconds -gt 3600) {
    throw "TokenTtlSeconds must be between 60 and 3600."
}

if (-not $ValidateOnly -and -not $PSCmdlet.ShouldProcess(
    "$ProjectId/$Region/$Service",
    "Deploy Stage 8 Ably realtime"
)) {
    Write-Host "Would validate the backend image and Ably secret, then deploy Stage 8."
    return
}

Invoke-Gcloud artifacts docker images describe $Image `
    --project=$ProjectId --format="value(image_summary.digest)"

$serviceJson = Invoke-Gcloud run services describe $Service `
    --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json

Invoke-Gcloud secrets versions describe $AblySecretVersion `
    --secret=$AblySecret --project=$ProjectId --format="value(name)" | Out-Null

if ($ValidateOnly) {
    Write-Host "Image, Cloud Run service, and Ably secret reference are valid."
    Write-Host "Secret value was not accessed or printed."
    return
}

$secretReference = "$AblySecret`:$AblySecretVersion"
$arguments = @(
    "run", "services", "update", $Service,
    "--project=$ProjectId",
    "--region=$Region",
    "--image=$Image",
    "--update-env-vars=REALTIME_PROVIDER=ably,ABLY_CHANNEL_PREFIX=$ChannelPrefix,ABLY_TOKEN_TTL_SECONDS=$TokenTtlSeconds,REALTIME_PUBLISH_ENABLED=true",
    "--update-secrets=ABLY_API_KEY=$secretReference"
)

$environment = @($serviceJson.spec.template.spec.containers[0].env)
$currentBinding = @($environment | Where-Object name -eq "ABLY_API_KEY") | Select-Object -Last 1
if ($null -ne $currentBinding -and -not $currentBinding.valueFrom) {
    $arguments += "--remove-env-vars=ABLY_API_KEY"
}

Invoke-Gcloud @arguments

$updatedService = Invoke-Gcloud run services describe $Service `
    --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json
$configured = @($updatedService.spec.template.spec.containers[0].env)
$provider = @($configured | Where-Object name -eq "REALTIME_PROVIDER") | Select-Object -Last 1
$secret = @($configured | Where-Object name -eq "ABLY_API_KEY") | Select-Object -Last 1

if ($provider.value -ne "ably") {
    throw "REALTIME_PROVIDER was not configured as ably."
}
if ($null -eq $secret -or -not $secret.valueFrom) {
    throw "ABLY_API_KEY was not configured as a Secret Manager reference."
}

Write-Host "Stage 8 backend deployment completed."
Write-Host "Revision: $($updatedService.status.latestCreatedRevisionName)"
Write-Host "URL: $($updatedService.status.url)"
Write-Host "ABLY_API_KEY is stored as a secret reference."
