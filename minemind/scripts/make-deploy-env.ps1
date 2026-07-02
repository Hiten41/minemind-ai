param(
  [Parameter(Mandatory = $true)]
  [string]$FrontendUrl,

  [Parameter(Mandatory = $true)]
  [string]$BackendUrl,

  [Parameter(Mandatory = $true)]
  [string]$GroqApiKey,

  [string]$CogneeBaseUrl = "",
  [string]$CogneeApiKey = "",
  [string]$StorageDir = "/data/minemind",
  [string]$EmbeddingEndpoint = "http://your-ollama-host:11434/api/embed"
)

$ErrorActionPreference = "Stop"

function Normalize-Url([string]$Url) {
  return $Url.Trim().TrimEnd("/")
}

$frontend = Normalize-Url $FrontendUrl
$backend = Normalize-Url $BackendUrl
$cogneeBase = if ($CogneeBaseUrl) { Normalize-Url $CogneeBaseUrl } else { "" }
$secretBytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
  $rng.GetBytes($secretBytes)
}
finally {
  $rng.Dispose()
}
$authSecret = ([System.BitConverter]::ToString($secretBytes) -replace "-", "").ToLowerInvariant()

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$outDir = Join-Path $root "deploy-env"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$backendEnv = @"
APP_ENV=production
FRONTEND_ORIGINS=$frontend
AUTH_SECRET=$authSecret
MINEMIND_STORAGE_DIR=$StorageDir

LLM_PROVIDER=groq
LLM_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=$GroqApiKey

COGNEE_BASE_URL=$cogneeBase
COGNEE_API_KEY=$CogneeApiKey

EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_ENDPOINT=$EmbeddingEndpoint
EMBEDDING_DIMENSIONS=768

COGNEE_VECTOR_DB_PROVIDER=lancedb
COGNEE_GRAPH_DB_PROVIDER=kuzu
COGNEE_SKIP_CONNECTION_TEST=true
"@

$frontendEnv = @"
NEXT_PUBLIC_API_BASE_URL=$backend
"@

$backendPath = Join-Path $outDir "backend.production.env"
$frontendPath = Join-Path $outDir "frontend.production.env"

Set-Content -Path $backendPath -Value $backendEnv -Encoding UTF8
Set-Content -Path $frontendPath -Value $frontendEnv -Encoding UTF8

Write-Host "Created:"
Write-Host $backendPath
Write-Host $frontendPath
Write-Host ""
Write-Host "Add these variables in your hosting provider dashboards."
