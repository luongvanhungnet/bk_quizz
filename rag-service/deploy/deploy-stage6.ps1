[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$ProjectId = "bkquiz-stg-235740",
    [string]$Region = "asia-southeast1",
    [string]$Service = "bkquiz-rag-api",
    [string]$RuntimeServiceAccount = "",
    [string]$EventServiceAccountName = "bkquiz-rag-events",
    [string]$Topic = "bkquiz-rag-indexing",
    [string]$Subscription = "bkquiz-rag-indexing-push",
    [string]$Queue = "bkquiz-rag-indexing",
    [string]$SchedulerJob = "bkquiz-rag-reconcile",
    [Parameter(Mandatory = $true)]
    [string]$Image,
    [switch]$ValidateOnly,
    [switch]$DisableCeleryPools
)

$ErrorActionPreference = "Stop"
$eventServiceAccount = "$EventServiceAccountName@$ProjectId.iam.gserviceaccount.com"

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
        $exists = $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    return $exists
}

if (-not $ValidateOnly -and -not $PSCmdlet.ShouldProcess(
    "$ProjectId/$Region/$Service",
    "Deploy Stage 6 cloud job transport"
)) {
    Write-Host "Would validate the image, detect the runtime service account, and deploy Stage 6."
    return
}

Invoke-Gcloud artifacts docker images describe $Image --project=$ProjectId --format="value(image_summary.digest)"
$existingService = Invoke-Gcloud run services describe $Service `
    --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json
$currentUrl = [string]$existingService.status.url
$detectedRuntimeServiceAccount = [string]$existingService.spec.template.spec.serviceAccountName
if (-not $RuntimeServiceAccount) {
    $RuntimeServiceAccount = $detectedRuntimeServiceAccount
}
if (-not $RuntimeServiceAccount) {
    throw "Cloud Run service does not have a runtime service account."
}
if (-not (Test-GcloudResource iam service-accounts describe $RuntimeServiceAccount --project=$ProjectId)) {
    throw "Runtime service account does not exist: $RuntimeServiceAccount. Detected on service: $detectedRuntimeServiceAccount"
}
if ($ValidateOnly) {
    Write-Host "Image and Cloud Run service are available."
    Write-Host "Runtime service account: $RuntimeServiceAccount"
    Write-Host "Stage 6 will configure Pub/Sub, Cloud Tasks, Cloud Scheduler, IAM, and the RAG revision."
    return
}

Invoke-Gcloud services enable `
    run.googleapis.com pubsub.googleapis.com cloudtasks.googleapis.com `
    cloudscheduler.googleapis.com iamcredentials.googleapis.com `
    --project=$ProjectId

if (-not (Test-GcloudResource iam service-accounts describe $eventServiceAccount --project=$ProjectId)) {
    Invoke-Gcloud iam service-accounts create $EventServiceAccountName `
        --project=$ProjectId `
        --display-name="BKQuiz RAG events"
}

$projectNumber = Invoke-Gcloud projects describe $ProjectId --format="value(projectNumber)"
if (-not $projectNumber) {
    throw "Unable to resolve Google Cloud project number."
}
$pubsubServiceAgent = "service-$projectNumber@gcp-sa-pubsub.iam.gserviceaccount.com"

Invoke-Gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$RuntimeServiceAccount" `
    --role="roles/pubsub.publisher" `
    --condition=None
Invoke-Gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$RuntimeServiceAccount" `
    --role="roles/cloudtasks.enqueuer" `
    --condition=None
Invoke-Gcloud iam service-accounts add-iam-policy-binding $eventServiceAccount `
    --project=$ProjectId `
    --member="serviceAccount:$RuntimeServiceAccount" `
    --role="roles/iam.serviceAccountUser"
Invoke-Gcloud iam service-accounts add-iam-policy-binding $eventServiceAccount `
    --project=$ProjectId `
    --member="serviceAccount:$pubsubServiceAgent" `
    --role="roles/iam.serviceAccountTokenCreator"
Invoke-Gcloud run services add-iam-policy-binding $Service `
    --project=$ProjectId `
    --region=$Region `
    --member="serviceAccount:$eventServiceAccount" `
    --role="roles/run.invoker"

if (-not (Test-GcloudResource pubsub topics describe $Topic --project=$ProjectId)) {
    Invoke-Gcloud pubsub topics create $Topic --project=$ProjectId
}

if (-not (Test-GcloudResource tasks queues describe $Queue --project=$ProjectId --location=$Region)) {
    Invoke-Gcloud tasks queues create $Queue `
        --project=$ProjectId `
        --location=$Region `
        --max-concurrent-dispatches=1 `
        --max-dispatches-per-second=1 `
        --max-attempts=4 `
        --min-backoff=10s `
        --max-backoff=300s `
        --max-doublings=4
}

$environment = @(
    "JOB_DISPATCH_BACKEND=gcp",
    "GCP_PROJECT_ID=$ProjectId",
    "GCP_REGION=$Region",
    "PUBSUB_INDEXING_TOPIC=$Topic",
    "CLOUD_TASKS_QUEUE=$Queue",
    "CLOUD_TASKS_WORKER_URL=$currentUrl",
    "CLOUD_TASKS_OIDC_AUDIENCE=$currentUrl",
    "CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL=$eventServiceAccount",
    "CLOUD_TASKS_DISPATCH_DEADLINE_SECONDS=900"
) -join ","

Invoke-Gcloud run services update $Service `
    --project=$ProjectId `
    --region=$Region `
    --image=$Image `
    "--update-env-vars=$environment"

$serviceUrl = Invoke-Gcloud run services describe $Service `
    --project=$ProjectId --region=$Region --format="value(status.url)"

if (-not (Test-GcloudResource pubsub subscriptions describe $Subscription --project=$ProjectId)) {
    Invoke-Gcloud pubsub subscriptions create $Subscription `
        --project=$ProjectId `
        --topic=$Topic `
        --push-endpoint="$serviceUrl/internal/events/indexing" `
        --push-auth-service-account=$eventServiceAccount `
        --push-auth-token-audience=$serviceUrl `
        --ack-deadline=30 `
        --min-retry-delay=10s `
        --max-retry-delay=300s
}
else {
    Invoke-Gcloud pubsub subscriptions modify-push-config $Subscription `
        --project=$ProjectId `
        --push-endpoint="$serviceUrl/internal/events/indexing" `
        --push-auth-service-account=$eventServiceAccount `
        --push-auth-token-audience=$serviceUrl
}

$schedulerUri = "$serviceUrl/internal/schedules/reconcile-indexing-jobs"
if (Test-GcloudResource scheduler jobs describe $SchedulerJob --project=$ProjectId --location=$Region) {
    Invoke-Gcloud scheduler jobs update http $SchedulerJob `
        --project=$ProjectId `
        --location=$Region `
        --schedule="*/1 * * * *" `
        --uri=$schedulerUri `
        --http-method=POST `
        --oidc-service-account-email=$eventServiceAccount `
        --oidc-token-audience=$serviceUrl `
        --headers="Content-Type=application/json" `
        --message-body="{}" `
        --time-zone="Etc/UTC"
}
else {
    Invoke-Gcloud scheduler jobs create http $SchedulerJob `
        --project=$ProjectId `
        --location=$Region `
        --schedule="*/1 * * * *" `
        --uri=$schedulerUri `
        --http-method=POST `
        --oidc-service-account-email=$eventServiceAccount `
        --oidc-token-audience=$serviceUrl `
        --headers="Content-Type=application/json" `
        --message-body="{}" `
        --time-zone="Etc/UTC"
}

if ($DisableCeleryPools) {
    Invoke-Gcloud run worker-pools update bkquiz-rag-worker `
        --project=$ProjectId --region=$Region --instances=0
    Invoke-Gcloud run worker-pools update bkquiz-rag-beat `
        --project=$ProjectId --region=$Region --instances=0
}

Write-Host "Stage 6 deployment completed."
Write-Host "RAG URL: $serviceUrl"
Write-Host "Keep Redis configured for locks and rate limits."
Write-Host "Disable Celery pools only after the smoke test succeeds."
