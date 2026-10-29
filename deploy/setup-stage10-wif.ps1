[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [string]$ProjectId = "bkquiz-stg-235740",
    [string]$Region = "asia-southeast1",
    [string]$BackendService = "bkquiz-api",
    [string]$RagService = "bkquiz-rag-api",
    [string]$Pool = "github-actions",
    [string]$Provider = "bkquiz",
    [string]$DeployServiceAccountName = "bkquiz-github-deployer",
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[^/]+/[^/]+$")]
    [string]$GitHubRepository,
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

function Get-RuntimeServiceAccount {
    param([string]$Service)
    $email = Invoke-Gcloud run services describe $Service `
        --project=$ProjectId --region=$Region `
        --format="value(spec.template.spec.serviceAccountName)"
    $email = ([string]$email).Trim()
    if ([string]::IsNullOrWhiteSpace($email)) {
        throw "Cloud Run service has no runtime service account: $Service"
    }
    return $email
}

$projectNumber = ([string](Invoke-Gcloud projects describe $ProjectId `
    --format="value(projectNumber)")).Trim()
$deployServiceAccount = "$DeployServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$backendRuntimeServiceAccount = Get-RuntimeServiceAccount $BackendService
$ragRuntimeServiceAccount = Get-RuntimeServiceAccount $RagService
$providerResource = "projects/$projectNumber/locations/global/workloadIdentityPools/$Pool/providers/$Provider"
$wifMember = "principalSet://iam.googleapis.com/projects/$projectNumber/locations/global/workloadIdentityPools/$Pool/attribute.repository/$GitHubRepository"

if ($ValidateOnly) {
    $required = @(
        (Test-GcloudResource iam service-accounts describe $deployServiceAccount --project=$ProjectId),
        (Test-GcloudResource iam workload-identity-pools describe $Pool --project=$ProjectId --location=global),
        (Test-GcloudResource iam workload-identity-pools providers describe $Provider --project=$ProjectId --location=global --workload-identity-pool=$Pool)
    )
    if ($required -contains $false) {
        throw "Stage 10 WIF resources are incomplete. Run this script without -ValidateOnly."
    }
    Write-Host "Stage 10 WIF resources exist."
    Write-Host "GCP_WIF_PROVIDER=$providerResource"
    Write-Host "GCP_DEPLOY_SERVICE_ACCOUNT=$deployServiceAccount"
    Write-Host "Backend runtime service account: $backendRuntimeServiceAccount"
    Write-Host "RAG runtime service account: $ragRuntimeServiceAccount"
    return
}

if (-not $PSCmdlet.ShouldProcess(
    "$ProjectId for GitHub repository $GitHubRepository",
    "Configure Stage 10 Workload Identity Federation and deploy permissions"
)) {
    Write-Host "Would create or update the GitHub OIDC provider and deployment IAM bindings."
    Write-Host "No service-account JSON key will be created."
    return
}

Invoke-Gcloud services enable `
    iamcredentials.googleapis.com sts.googleapis.com run.googleapis.com `
    cloudbuild.googleapis.com artifactregistry.googleapis.com `
    secretmanager.googleapis.com --project=$ProjectId

if (-not (Test-GcloudResource iam service-accounts describe $deployServiceAccount --project=$ProjectId)) {
    Invoke-Gcloud iam service-accounts create $DeployServiceAccountName `
        --project=$ProjectId `
        --display-name="BKQuiz GitHub release deployer"
}

if (-not (Test-GcloudResource iam workload-identity-pools describe `
    $Pool --project=$ProjectId --location=global)) {
    Invoke-Gcloud iam workload-identity-pools create $Pool `
        --project=$ProjectId --location=global `
        --display-name="GitHub Actions"
}

if (-not (Test-GcloudResource iam workload-identity-pools providers describe `
    $Provider --project=$ProjectId --location=global `
    --workload-identity-pool=$Pool)) {
    Invoke-Gcloud iam workload-identity-pools providers create-oidc $Provider `
        --project=$ProjectId --location=global `
        --workload-identity-pool=$Pool `
        --display-name="BKQuiz GitHub repository" `
        --issuer-uri="https://token.actions.githubusercontent.com" `
        --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.ref=assertion.ref" `
        --attribute-condition="assertion.repository=='$GitHubRepository'"
}

Invoke-Gcloud iam service-accounts add-iam-policy-binding $deployServiceAccount `
    --project=$ProjectId --role="roles/iam.workloadIdentityUser" `
    --member=$wifMember

foreach ($role in @(
    "roles/run.admin",
    "roles/cloudbuild.builds.editor",
    "roles/artifactregistry.writer",
    "roles/secretmanager.viewer",
    "roles/serviceusage.serviceUsageConsumer"
)) {
    Invoke-Gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$deployServiceAccount" `
        --role=$role --condition=None
}

foreach ($runtimeServiceAccount in @($backendRuntimeServiceAccount, $ragRuntimeServiceAccount)) {
    Invoke-Gcloud iam service-accounts add-iam-policy-binding $runtimeServiceAccount `
        --project=$ProjectId `
        --member="serviceAccount:$deployServiceAccount" `
        --role="roles/iam.serviceAccountUser"
}

Invoke-Gcloud run services add-iam-policy-binding $RagService `
    --project=$ProjectId --region=$Region `
    --member="serviceAccount:$deployServiceAccount" `
    --role="roles/run.invoker"

Write-Host "Stage 10 Workload Identity Federation is configured."
Write-Host "Add these non-secret values to each GitHub Environment:"
Write-Host "GCP_WIF_PROVIDER=$providerResource"
Write-Host "GCP_DEPLOY_SERVICE_ACCOUNT=$deployServiceAccount"
Write-Host "GCP_BACKEND_RUNTIME_SERVICE_ACCOUNT=$backendRuntimeServiceAccount"
Write-Host "GCP_RAG_RUNTIME_SERVICE_ACCOUNT=$ragRuntimeServiceAccount"
Write-Host "No service-account key was created or printed."
