# =============================================================================
# deploy.ps1 - Deploiement de l'API "Enterprise AI Data Analyst" sur Google Cloud Run
# -----------------------------------------------------------------------------
# Architecture serverless : l'image Docker est construite par Cloud Build, poussee
# dans Artifact Registry, puis lancee par Cloud Run (HTTPS auto, scale-to-zero).
#
# Pre-requis :
#   - Google Cloud SDK (gcloud) installe  : https://cloud.google.com/sdk/docs/install
#   - Un projet GCP avec facturation / credits gratuits actives
#   - Docker N'EST PAS necessaire (Cloud Build construit l'image a distance)
#
# Usage :
#   1. Renseigne $ProjectId ci-dessous (et eventuellement $Region).
#   2. Mets ta cle Gemini dans src/.env (ligne : GCP_API_KEY=...).
#   3. Lance :  powershell -ExecutionPolicy Bypass -File .\deploy.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

# -----------------------------------------------------------------------------
# 0) Configuration - adapte ces valeurs a ton environnement
# -----------------------------------------------------------------------------
$ProjectId = "TON_PROJECT_ID"        # <-- REMPLACE par l'ID de ton projet GCP
$Region    = "europe-west1"          # Region Cloud Run / Artifact Registry
$Repo      = "app-images"            # Nom du depot Artifact Registry
$Service   = "enterprise-ai-analyst" # Nom du service Cloud Run
$SecretName = "gcp-api-key"          # Nom du secret dans Secret Manager

# (Optionnel) Qdrant Cloud pour la recherche vectorielle.
#   - Laisse $QdrantUrl vide pour un deploiement SQL uniquement (pas de vectoriel).
#   - Sinon mets l'endpoint du cluster (avec :6333) et ajoute QDRANT_API_KEY=... dans src/.env.
$QdrantUrl        = ""               # ex: https://xxxx.gcp.cloud.qdrant.io:6333
$QdrantSecretName = "qdrant-key"     # Nom du secret Qdrant dans Secret Manager

Write-Host "==> Projet: $ProjectId | Region: $Region | Service: $Service" -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# 1) Authentification et selection du projet
# -----------------------------------------------------------------------------
# gcloud auth login ouvre le navigateur ; commente la ligne si deja authentifie.
gcloud auth login
gcloud config set project $ProjectId

# -----------------------------------------------------------------------------
# 2) Activation des APIs necessaires
#    run            -> Cloud Run | artifactregistry -> registre d'images
#    cloudbuild     -> build distant | secretmanager -> stockage de la cle Gemini
# -----------------------------------------------------------------------------
gcloud services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    secretmanager.googleapis.com

# -----------------------------------------------------------------------------
# 3) Creation du depot Artifact Registry (idempotent : ignore si deja present)
# -----------------------------------------------------------------------------
$repoExists = $true
try { gcloud artifacts repositories describe $Repo --location $Region 2>$null | Out-Null }
catch { $repoExists = $false }

if (-not $repoExists) {
    Write-Host "==> Creation du depot Artifact Registry '$Repo'..." -ForegroundColor Cyan
    gcloud artifacts repositories create $Repo `
        --repository-format=docker `
        --location=$Region `
        --description="Enterprise AI analyst images"
} else {
    Write-Host "==> Depot '$Repo' deja existant, on continue." -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 4) Creation du secret Gemini dans Secret Manager (lu depuis src/.env)
#    La cle n'est JAMAIS ecrite en clair dans la commande de deploiement.
# -----------------------------------------------------------------------------
$envFile = Join-Path $PSScriptRoot "src\.env"
if (-not (Test-Path $envFile)) { throw "Fichier introuvable : $envFile (ajoute GCP_API_KEY=...)" }

$apiKey = (Get-Content $envFile |
    Where-Object { $_ -match '^\s*GCP_API_KEY\s*=' } |
    Select-Object -First 1) -replace '^\s*GCP_API_KEY\s*=\s*', ''
$apiKey = $apiKey.Trim()
if ([string]::IsNullOrWhiteSpace($apiKey)) { throw "GCP_API_KEY est vide dans $envFile" }

$secretExists = $true
try { gcloud secrets describe $SecretName 2>$null | Out-Null }
catch { $secretExists = $false }

# Ecrire la cle dans un fichier temporaire SANS retour a la ligne : un newline
# final rend l'en-tete gRPC du client Gemini invalide ("Illegal header value").
$keyFile = Join-Path $env:TEMP "gcp_api_key.txt"
[System.IO.File]::WriteAllText($keyFile, $apiKey)
try {
    if (-not $secretExists) {
        Write-Host "==> Creation du secret '$SecretName'..." -ForegroundColor Cyan
        gcloud secrets create $SecretName --data-file="$keyFile"
    } else {
        Write-Host "==> Ajout d'une nouvelle version au secret '$SecretName'..." -ForegroundColor Yellow
        gcloud secrets versions add $SecretName --data-file="$keyFile"
    }
}
finally {
    Remove-Item $keyFile -Force -ErrorAction SilentlyContinue
}

# -----------------------------------------------------------------------------
# 5) Autoriser le compte de service Cloud Run a lire le secret
#    Le service tourne sous le compte de service Compute par defaut :
#    <PROJECT_NUMBER>-compute@developer.gserviceaccount.com
#    Il lui faut le role 'Secret Manager Secret Accessor' pour lire la cle.
# -----------------------------------------------------------------------------
$ProjectNumber = gcloud projects describe $ProjectId --format "value(projectNumber)"
$RuntimeSa = "$ProjectNumber-compute@developer.gserviceaccount.com"
Write-Host "==> Octroi de roles/secretmanager.secretAccessor a $RuntimeSa..." -ForegroundColor Cyan
gcloud secrets add-iam-policy-binding $SecretName `
    --member="serviceAccount:$RuntimeSa" `
    --role="roles/secretmanager.secretAccessor"

# -----------------------------------------------------------------------------
# 5b) (Optionnel) Secret + acces pour la cle Qdrant Cloud
#     Active uniquement si $QdrantUrl est renseigne. La cle est lue depuis
#     src/.env (ligne QDRANT_API_KEY=...) et stockee SANS retour a la ligne.
# -----------------------------------------------------------------------------
$EnvVars = "AGENT_MODEL=gemini-2.5-flash,FILTER_EXTRACTION_MODEL=gemini-2.5-flash-lite"
$Secrets = "GCP_API_KEY=$SecretName`:latest"

# -----------------------------------------------------------------------------
# 5a) (Optionnel) Cles Gemini de secours (fallback automatique sur 429/timeout)
#     Pour chaque GCP_API_KEY2/3/4 present dans src/.env, on cree un secret dedie
#     (sans newline) et on l'injecte sous le meme nom de variable. Le code
#     (src/agent/graph.py) bascule sur la cle suivante quand une est rate-limitee.
# -----------------------------------------------------------------------------
foreach ($n in 2, 3, 4) {
    $envVarName = "GCP_API_KEY$n"
    $fbKey = (Get-Content $envFile |
        Where-Object { $_ -match "^\s*$envVarName\s*=" } |
        Select-Object -First 1) -replace "^\s*$envVarName\s*=\s*", ''
    $fbKey = $fbKey.Trim()
    if ([string]::IsNullOrWhiteSpace($fbKey)) { continue }

    $fbSecret = "gcp-api-key-$n"
    gcloud secrets describe $fbSecret 2>$null | Out-Null
    $fbExists = ($LASTEXITCODE -eq 0)
    $fbFile = Join-Path $env:TEMP "$fbSecret.txt"
    [System.IO.File]::WriteAllText($fbFile, $fbKey)
    try {
        if (-not $fbExists) {
            Write-Host "==> Creation du secret '$fbSecret'..." -ForegroundColor Cyan
            gcloud secrets create $fbSecret --data-file="$fbFile"
        } else {
            Write-Host "==> Nouvelle version du secret '$fbSecret'..." -ForegroundColor Yellow
            gcloud secrets versions add $fbSecret --data-file="$fbFile"
        }
    }
    finally {
        Remove-Item $fbFile -Force -ErrorAction SilentlyContinue
    }

    gcloud secrets add-iam-policy-binding $fbSecret `
        --member="serviceAccount:$RuntimeSa" `
        --role="roles/secretmanager.secretAccessor"

    $Secrets = "$Secrets,$envVarName=$fbSecret`:latest"
}

if (-not [string]::IsNullOrWhiteSpace($QdrantUrl)) {
    $qKey = (Get-Content $envFile |
        Where-Object { $_ -match '^\s*QDRANT_API_KEY\s*=' } |
        Select-Object -First 1) -replace '^\s*QDRANT_API_KEY\s*=\s*', ''
    $qKey = $qKey.Trim()
    if ([string]::IsNullOrWhiteSpace($qKey)) { throw "QDRANT_API_KEY est vide dans $envFile" }

    gcloud secrets describe $QdrantSecretName 2>$null | Out-Null
    $qExists = ($LASTEXITCODE -eq 0)
    $qFile = Join-Path $env:TEMP "qdrant_api_key.txt"
    [System.IO.File]::WriteAllText($qFile, $qKey)
    try {
        if (-not $qExists) {
            Write-Host "==> Creation du secret '$QdrantSecretName'..." -ForegroundColor Cyan
            gcloud secrets create $QdrantSecretName --data-file="$qFile"
        } else {
            Write-Host "==> Ajout d'une nouvelle version au secret '$QdrantSecretName'..." -ForegroundColor Yellow
            gcloud secrets versions add $QdrantSecretName --data-file="$qFile"
        }
    }
    finally {
        Remove-Item $qFile -Force -ErrorAction SilentlyContinue
    }

    gcloud secrets add-iam-policy-binding $QdrantSecretName `
        --member="serviceAccount:$RuntimeSa" `
        --role="roles/secretmanager.secretAccessor"

    $EnvVars = "$EnvVars,QDRANT_URL=$QdrantUrl"
    $Secrets = "$Secrets,QDRANT_API_KEY=$QdrantSecretName`:latest"
}

# -----------------------------------------------------------------------------
# 6) Build + deploiement sur Cloud Run en une commande
#    --source .        : Cloud Build lit le Dockerfile et pousse l'image
#    --port 8000       : l'app ecoute sur 8000 (le Dockerfile expose ce port)
#    --memory 2Gi      : torch + sentence-transformers sont gourmands au demarrage
#    --set-secrets     : injecte la cle Gemini comme variable d'env GCP_API_KEY
#    --allow-unauthenticated : URL publique (pratique pour une demo)
# -----------------------------------------------------------------------------
gcloud run deploy $Service `
    --source . `
    --region $Region `
    --port 8000 `
    --allow-unauthenticated `
    --memory 2Gi `
    --cpu 2 `
    --timeout 300 `
    --set-env-vars $EnvVars `
    --set-secrets $Secrets

# -----------------------------------------------------------------------------
# 7) Recuperation de l'URL publique et rappel des commandes de test
# -----------------------------------------------------------------------------
$Url = gcloud run services describe $Service --region $Region --format "value(status.url)"
Write-Host ""
Write-Host "==> Service deploye : $Url" -ForegroundColor Green
Write-Host "    Health check :" -ForegroundColor Green
Write-Host "      curl `"$Url/health`""
Write-Host "    Question a l'agent :" -ForegroundColor Green
Write-Host "      curl -X POST `"$Url/ask`" -H `"Content-Type: application/json`" -d '{\"question\":\"What was Apple revenue in 2024?\",\"limit\":5}'"
Write-Host "    Swagger UI : $Url/docs" -ForegroundColor Green

# -----------------------------------------------------------------------------
# 8) (Optionnel) Supprimer le service apres la demo pour eviter tout cout
# -----------------------------------------------------------------------------
# gcloud run services delete $Service --region $Region
