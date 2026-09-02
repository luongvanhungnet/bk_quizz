[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [string]$ProjectId = "bkquiz-stg-235740",
    [string]$Region = "asia-southeast1",
    [string]$Service = "bkquiz-api",
    [string]$SecretName = "bkquiz-resend-api-key",
    [string]$Sender = "BKQuiz <noreply@luongvanhungnet.xyz>",
    [string]$ApiUrl = "https://api.resend.com/emails",
    [string]$TestRecipient = "",
    [SecureString]$ApiKey,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

function Invoke-Gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & gcloud @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    if ($exitCode -ne 0) {
        throw "gcloud command failed: gcloud $($Arguments -join ' ')"
    }
}

function Test-GcloudResource {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & gcloud @Arguments *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
}

function ConvertTo-PlainText {
    param([SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Get-ServiceConfiguration {
    return Invoke-Gcloud run services describe $Service `
        --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json
}

$serviceConfiguration = Get-ServiceConfiguration
$runtimeServiceAccount = ([string]$serviceConfiguration.spec.template.spec.serviceAccountName).Trim()
if ([string]::IsNullOrWhiteSpace($runtimeServiceAccount)) {
    throw "Cloud Run service has no runtime service account: $Service"
}

if ($ValidateOnly) {
    $environment = @($serviceConfiguration.spec.template.spec.containers[0].env)
    $keyBinding = @($environment | Where-Object name -eq "RESEND_API_TOKEN") | Select-Object -Last 1
    $senderBinding = @($environment | Where-Object name -eq "APP_MAIL_FROM") | Select-Object -Last 1
    if ($null -eq $keyBinding -or -not $keyBinding.valueFrom) {
        throw "RESEND_API_TOKEN is not bound to Secret Manager on $Service."
    }
    $boundSecret = [string]$keyBinding.valueFrom.secretKeyRef.name
    $boundVersion = [string]$keyBinding.valueFrom.secretKeyRef.key
    if (-not (Test-GcloudResource secrets versions describe $boundVersion `
        --secret=$boundSecret --project=$ProjectId)) {
        throw "The configured Resend secret version does not exist or is disabled."
    }
    if ($null -eq $senderBinding -or [string]::IsNullOrWhiteSpace([string]$senderBinding.value)) {
        throw "APP_MAIL_FROM is missing from $Service."
    }
    Write-Host "Resend Cloud Run binding is structurally valid."
    Write-Host "Secret: $boundSecret version $boundVersion"
    Write-Host "Sender: $($senderBinding.value)"
    Write-Host "This check does not read or print the API key. Use -TestRecipient while rotating to test delivery."
    return
}

if (-not $PSCmdlet.ShouldProcess(
    "$ProjectId/$Region/$Service",
    "Rotate the Resend API key, configure the verified sender, and create a Cloud Run revision"
)) {
    Write-Host "Would create a new secret version and bind RESEND_API_TOKEN to $SecretName."
    Write-Host "No key would be printed."
    return
}

if ($null -eq $ApiKey) {
    $ApiKey = Read-Host "Paste the new Resend API key" -AsSecureString
}
$plainApiKey = ConvertTo-PlainText $ApiKey
if ([string]::IsNullOrWhiteSpace($plainApiKey) -or -not $plainApiKey.StartsWith("re_")) {
    $plainApiKey = $null
    throw "The Resend API key must be a non-empty key beginning with re_."
}
if ($Sender -notmatch "^[^<>]+<[^<>@\s]+@[^<>@\s]+>$" -and
    $Sender -notmatch "^[^@\s]+@[^@\s]+$") {
    $plainApiKey = $null
    throw "Sender must be an email address or Display Name <email@verified-domain>."
}

try {
    if (-not [string]::IsNullOrWhiteSpace($TestRecipient)) {
        $headers = @{
            Authorization = "Bearer $plainApiKey"
            "Idempotency-Key" = "bkquiz-resend-config/$([Guid]::NewGuid())"
        }
        $body = [ordered]@{
            from = $Sender
            to = $TestRecipient
            subject = "BKQuiz - kiem tra cau hinh email"
            text = "Day la email kiem tra cau hinh Resend cua BKQuiz."
            html = "<p>Day la email kiem tra cau hinh Resend cua BKQuiz.</p>"
        } | ConvertTo-Json -Compress
        try {
            $testResponse = Invoke-RestMethod -Method Post -Uri $ApiUrl `
                -Headers $headers -ContentType "application/json" -Body $body
        }
        catch {
            throw "Resend preflight send failed. Verify the new key, the exact sender domain, and recipient policy before updating Cloud Run."
        }
        if ($null -eq $testResponse.id -or [string]::IsNullOrWhiteSpace([string]$testResponse.id)) {
            throw "Resend preflight returned no email ID. Cloud Run was not changed."
        }
        Write-Host "Resend accepted the preflight email."
    }

    if (-not (Test-GcloudResource secrets describe $SecretName --project=$ProjectId)) {
        Invoke-Gcloud secrets create $SecretName `
            --project=$ProjectId --replication-policy=automatic | Out-Null
    }

    $temporaryFile = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($temporaryFile, $plainApiKey, [Text.UTF8Encoding]::new($false))
        $versionResource = Invoke-Gcloud secrets versions add $SecretName `
            --project=$ProjectId --data-file=$temporaryFile --format="value(name)"
    }
    finally {
        if (Test-Path $temporaryFile) {
            [IO.File]::WriteAllText($temporaryFile, "", [Text.UTF8Encoding]::new($false))
            Remove-Item $temporaryFile -Force -ErrorAction SilentlyContinue
        }
    }
    $secretVersion = ([string]$versionResource).Trim().Split("/")[-1]
    if ([string]::IsNullOrWhiteSpace($secretVersion)) {
        throw "Unable to determine the new Resend secret version."
    }

    Invoke-Gcloud secrets add-iam-policy-binding $SecretName `
        --project=$ProjectId `
        --member="serviceAccount:$runtimeServiceAccount" `
        --role="roles/secretmanager.secretAccessor" | Out-Null

    $environment = @($serviceConfiguration.spec.template.spec.containers[0].env)
    $senderBinding = @($environment | Where-Object name -eq "APP_MAIL_FROM") | Select-Object -Last 1
    if ($null -ne $senderBinding -and $senderBinding.valueFrom) {
        throw "APP_MAIL_FROM is currently a secret binding. Convert it to a literal manually before running this script."
    }
    $apiUrlBinding = @($environment | Where-Object name -eq "RESEND_API_URL") | Select-Object -Last 1
    $literalUpdates = @(
        "APP_MAIL_FROM=$Sender",
        "RESEND_CONNECT_TIMEOUT=30s",
        "RESEND_READ_TIMEOUT=45s",
        "RESEND_NETWORK_RETRY_DELAY=30s"
    )
    if ($null -eq $apiUrlBinding -or -not $apiUrlBinding.valueFrom) {
        $literalUpdates += "RESEND_API_URL=$ApiUrl"
    }

    Invoke-Gcloud run services update $Service `
        --project=$ProjectId --region=$Region `
        "--update-secrets=RESEND_API_TOKEN=$SecretName`:$secretVersion" `
        "--update-env-vars=$($literalUpdates -join ',')" | Out-Null

    $updated = Get-ServiceConfiguration
    $updatedEnvironment = @($updated.spec.template.spec.containers[0].env)
    $updatedKey = @($updatedEnvironment | Where-Object name -eq "RESEND_API_TOKEN") | Select-Object -Last 1
    if ($null -eq $updatedKey -or -not $updatedKey.valueFrom `
        -or $updatedKey.valueFrom.secretKeyRef.name -ne $SecretName `
        -or [string]$updatedKey.valueFrom.secretKeyRef.key -ne $secretVersion) {
        throw "Cloud Run did not bind the new Resend secret version."
    }

    Write-Host "Resend configuration updated successfully."
    Write-Host "Secret: $SecretName version $secretVersion"
    Write-Host "Revision: $($updated.status.latestCreatedRevisionName)"
    Write-Host "Sender: $Sender"
    Write-Host "The API key was not printed."
}
finally {
    $plainApiKey = $null
}
