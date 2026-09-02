# Giai đoạn 10 — CI/CD release bằng GitHub Actions

## Kết quả triển khai

Giai đoạn 10 bổ sung pipeline phát hành thủ công, có kiểm soát tại
`.github/workflows/release.yml`:

1. chạy toàn bộ quality gate Spring, React và RAG;
2. đăng nhập Google Cloud bằng GitHub OIDC + Workload Identity Federation,
   không dùng service-account JSON key;
3. build ba image bất biến theo Git commit SHA: Spring, Flyway và RAG;
4. chạy Flyway và Alembic bằng hai Cloud Run Job, mỗi job `max-retries=0`;
5. deploy RAG trước, smoke test private endpoint bằng Google ID token;
6. deploy Spring rồi kiểm tra liveness/readiness;
7. nếu smoke test lỗi, tự chuyển traffic về revision sẵn sàng trước đó;
8. build và publish `frontend/dist` lên Cloudflare Pages;
9. lưu release manifest để rollback/audit.

Pipeline chỉ cập nhật image của hai Cloud Run service. Toàn bộ env var, secret,
service account, scaling, probe và IAM đã cấu hình ở giai đoạn 1–9 được giữ
nguyên. Ollama tiếp tục bị tắt trong production.

## 1. File mới

- `.github/workflows/release.yml`: release pipeline.
- `backend/Dockerfile.migrate`: image Flyway chỉ chứa migration Spring.
- `backend/cloudbuild.migrate.yaml`: build migration image bằng Cloud Build.
- `backend/.gcloudignore`: loại build output và cấu hình local khỏi Cloud Build context.
- `deploy/setup-stage10-wif.ps1`: tạo WIF và IAM tối thiểu cần cho pipeline.

`gha-creds-*.json` đã được thêm vào `.gitignore` để file credential tạm do
GitHub auth action tạo ra không thể bị commit nhầm.

## 2. Chuẩn bị Google Cloud một lần

Đăng nhập bằng tài khoản có quyền quản trị IAM của project:

```powershell
cd D:\BKQuiz

$PROJECT_ID = 'bkquiz-stg-235740'
$REGION = 'asia-southeast1'
$GITHUB_REPOSITORY = 'deepdev-hub/bk_quizz'

gcloud config set project $PROJECT_ID
gcloud auth list

.\deploy\setup-stage10-wif.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -GitHubRepository $GITHUB_REPOSITORY `
  -WhatIf

.\deploy\setup-stage10-wif.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -GitHubRepository $GITHUB_REPOSITORY

.\deploy\setup-stage10-wif.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -GitHubRepository $GITHUB_REPOSITORY `
  -ValidateOnly
```

Giá trị trên khớp remote `origin` hiện tại của BKQuiz. Điều kiện OIDC khóa
chính xác repository này; token từ repository khác không thể impersonate deploy
service account.

Script tự đọc service account runtime đang gắn với `bkquiz-api` và
`bkquiz-rag-api`; không tự đoán email. Nó không tạo hoặc tải JSON key.

## 3. Cho migration job đọc direct database secrets

Workflow không đọc giá trị secret. Nó chỉ gắn Secret Manager reference vào
Cloud Run Job. Runtime service account của từng job phải có `secretAccessor`
trên các secret tương ứng.

Ví dụ tên secret (đổi theo tên thật trong project):

```powershell
$BACKEND_SA = gcloud run services describe bkquiz-api `
  --region=$REGION --format='value(spec.template.spec.serviceAccountName)'
$RAG_SA = gcloud run services describe bkquiz-rag-api `
  --region=$REGION --format='value(spec.template.spec.serviceAccountName)'

$BACKEND_SECRETS = @(
  'bkquiz-database-url-direct',
  'bkquiz-database-username',
  'bkquiz-database-password'
)
foreach ($SECRET in $BACKEND_SECRETS) {
  gcloud secrets add-iam-policy-binding $SECRET `
    --project=$PROJECT_ID `
    --member="serviceAccount:$BACKEND_SA" `
    --role='roles/secretmanager.secretAccessor'
}

gcloud secrets add-iam-policy-binding bkquiz-rag-database-url-direct `
  --project=$PROJECT_ID `
  --member="serviceAccount:$RAG_SA" `
  --role='roles/secretmanager.secretAccessor'
```

Direct URL của Spring phải là JDBC URL có `sslmode=require`. Direct URL của RAG
phải là SQLAlchemy PostgreSQL URL. Runtime service vẫn dùng pooled URL; chỉ
migration job dùng direct endpoint.

## 4. Tạo GitHub Environments

Trong GitHub repository, mở **Settings → Environments** và tạo:

- `staging`;
- `production`.

Khuyến nghị đặt required reviewer cho `production`. Mỗi environment thêm các
Variables sau:

| Variable | Giá trị mẫu staging |
|---|---|
| `GCP_PROJECT_ID` | `bkquiz-stg-235740` |
| `GCP_REGION` | `asia-southeast1` |
| `GCP_ARTIFACT_REPOSITORY` | `bkquiz` |
| `GCP_WIF_PROVIDER` | output đầy đủ từ setup script |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | output email từ setup script |
| `GCP_BACKEND_SERVICE` | `bkquiz-api` |
| `GCP_RAG_SERVICE` | `bkquiz-rag-api` |
| `GCP_BACKEND_MIGRATION_JOB` | `bkquiz-db-migrate` |
| `GCP_RAG_MIGRATION_JOB` | `bkquiz-rag-migrate` |
| `GCP_BACKEND_RUNTIME_SERVICE_ACCOUNT` | output từ setup script |
| `GCP_RAG_RUNTIME_SERVICE_ACCOUNT` | output từ setup script |
| `BACKEND_DATABASE_DIRECT_URL_SECRET_REF` | `bkquiz-database-url-direct:1` |
| `BACKEND_DATABASE_USERNAME_SECRET_REF` | `bkquiz-database-username:latest` |
| `BACKEND_DATABASE_PASSWORD_SECRET_REF` | `bkquiz-database-password:latest` |
| `RAG_DATABASE_DIRECT_URL_SECRET_REF` | `bkquiz-rag-database-url-direct:1` |
| `VITE_API_BASE_URL` | URL HTTPS của `bkquiz-api` |
| `VITE_API_SAME_ORIGIN_PROXY` | `false` |
| `CLOUDFLARE_PAGES_PROJECT` | tên Pages project |

Secret reference nên pin version số trong production thay vì `latest`; bảng
chỉ giữ `latest` cho hai secret đã có từ cấu hình cũ.

Mỗi environment thêm hai GitHub Secrets:

- `CLOUDFLARE_API_TOKEN` — token chỉ có quyền Cloudflare Pages Edit cho account;
- `CLOUDFLARE_ACCOUNT_ID`.

Không đưa GCP key, Neon password, R2 key, Gemini key, Ably key hoặc Resend key
vào GitHub. Chúng tiếp tục nằm trong Google Secret Manager.

Nếu đã cài GitHub CLI, có thể đặt variable như sau:

```powershell
$GH_ENV = 'staging'
$GH_REPO = 'deepdev-hub/bk_quizz'

gh variable set GCP_PROJECT_ID --env $GH_ENV --repo $GH_REPO --body $PROJECT_ID
gh variable set GCP_REGION --env $GH_ENV --repo $GH_REPO --body $REGION
gh variable set GCP_BACKEND_SERVICE --env $GH_ENV --repo $GH_REPO --body 'bkquiz-api'
gh variable set GCP_RAG_SERVICE --env $GH_ENV --repo $GH_REPO --body 'bkquiz-rag-api'
gh secret set CLOUDFLARE_API_TOKEN --env $GH_ENV --repo $GH_REPO
gh secret set CLOUDFLARE_ACCOUNT_ID --env $GH_ENV --repo $GH_REPO
```

Hai lệnh `gh secret set` đọc giá trị tương tác, không ghi secret vào history.

## 5. Chạy Giai đoạn 10

Commit và push các file Stage 10 lên repository. Sau đó:

1. mở GitHub → **Actions**;
2. chọn **Release BKQuiz**;
3. nhấn **Run workflow**;
4. chọn `staging`;
5. giữ `run_migrations=true` ở lần deploy có migration mới;
6. giữ `deploy_frontend=true` nếu muốn cập nhật Cloudflare Pages;
7. theo dõi lần lượt `Quality gates`, `Migrate and deploy Cloud Run`, và
   `Deploy Cloudflare Pages`.

Có thể chạy bằng GitHub CLI:

```powershell
gh workflow run release.yml `
  --repo $GH_REPO `
  --ref main `
  -f environment=staging `
  -f run_migrations=true `
  -f deploy_frontend=true

gh run watch --repo $GH_REPO
```

Production chỉ chạy từ branch `main`. GitHub Environment approval là cổng xác
nhận trước deploy production.

## 6. Kiểm tra sau release

```powershell
$BACKEND_URL = gcloud run services describe bkquiz-api `
  --project=$PROJECT_ID --region=$REGION --format='value(status.url)'
$RAG_URL = gcloud run services describe bkquiz-rag-api `
  --project=$PROJECT_ID --region=$REGION --format='value(status.url)'

Invoke-RestMethod "$BACKEND_URL/actuator/health/liveness"
Invoke-RestMethod "$BACKEND_URL/actuator/health/readiness"

$RAG_TOKEN = gcloud auth print-identity-token --audiences=$RAG_URL
Invoke-RestMethod "$RAG_URL/health/live" `
  -Headers @{ Authorization = "Bearer $RAG_TOKEN" }
```

Tiếp tục smoke test nghiệp vụ trên frontend:

1. đăng nhập và refresh access token;
2. upload/reindex một tài liệu;
3. tạo Quiz trống và sinh thêm một câu;
4. mở lớp học và kiểm tra Ably realtime;
5. upload avatar và xác nhận object có trong R2.

## 7. Rollback

Nếu smoke test trong workflow thất bại, workflow tự đưa traffic hai service về
`latestReadyRevisionName` đã ghi trước deploy. Release manifest artifact lưu tên
hai revision đó.

Rollback thủ công:

```powershell
gcloud run revisions list --service=bkquiz-api `
  --project=$PROJECT_ID --region=$REGION
gcloud run revisions list --service=bkquiz-rag-api `
  --project=$PROJECT_ID --region=$REGION

gcloud run services update-traffic bkquiz-api `
  --project=$PROJECT_ID --region=$REGION `
  --to-revisions='<backend-previous-revision>=100'

gcloud run services update-traffic bkquiz-rag-api `
  --project=$PROJECT_ID --region=$REGION `
  --to-revisions='<rag-previous-revision>=100'
```

Cloudflare Pages cho phép rollback deployment trong dashboard. Database
migration là forward-only: không chạy `flyway undo` hoặc downgrade Alembic tự
động. Nếu migration không backward-compatible, khôi phục Neon branch/PITR theo
runbook Stage 9 rồi mới đổi traffic.

## 8. Kiểm tra cục bộ trước khi push

```powershell
cd D:\BKQuiz\backend
.\mvnw.cmd verify

cd D:\BKQuiz\frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build

cd D:\BKQuiz\rag-service
python -m pytest -q
python -m ruff check app tests scripts integration
python -m mypy
python -m pip check
```

Tài liệu chính thức:

- GitHub Actions auth với Workload Identity Federation:
  https://github.com/google-github-actions/auth
- Google Cloud WIF cho deployment pipelines:
  https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
- Cloud Run rollback/traffic migration:
  https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration
- Cloudflare Wrangler Action:
  https://github.com/cloudflare/wrangler-action
