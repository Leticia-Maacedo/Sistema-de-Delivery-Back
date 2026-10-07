$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       ENTREGAFOOD - INICIALIZADOR" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ========================================
# CONFIGURACOES
# ========================================

$BackDir = $PSScriptRoot
$FrontDir = Join-Path (Split-Path $BackDir -Parent) "Sistema-de-Delivery-Front-DEV"

$EnvFile = Join-Path $BackDir ".env"

# ========================================
# VERIFICAR PROGRAMAS
# ========================================

Write-Host "[1/7] Verificando Docker..." -ForegroundColor Yellow

docker --version
if ($LASTEXITCODE -ne 0) {
    throw "Docker nao encontrado. Instale o Docker Desktop."
}

Write-Host "[2/7] Verificando Python..." -ForegroundColor Yellow

python --version
if ($LASTEXITCODE -ne 0) {
    throw "Python nao encontrado."
}

Write-Host "[3/7] Verificando Node.js..." -ForegroundColor Yellow

node --version
if ($LASTEXITCODE -ne 0) {
    throw "Node.js nao encontrado."
}

# ========================================
# CRIAR .ENV AUTOMATICAMENTE
# ========================================

Write-Host "[4/7] Verificando configuracao do Back..." -ForegroundColor Yellow

if (-not (Test-Path $EnvFile)) {

    Write-Host ""
    Write-Host "Primeira configuracao do EntregaFood." -ForegroundColor Cyan
    Write-Host "Vamos criar o arquivo .env automaticamente." -ForegroundColor Cyan
    Write-Host ""

    $FacebookSecret = Read-Host "Digite o FACEBOOK_APP_SECRET"
    $GoogleSecret = Read-Host "Digite o GOOGLE_CLIENT_SECRET"

    @"
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/entregafood

JWT_SECRET=troque-esta-chave-por-uma-aleatoria-e-longa
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175

GOOGLE_CLIENT_ID=703641287087-it47cchc5egbh89uc4k8cgf65btuhd2d.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=$GoogleSecret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

FRONTEND_URL=http://localhost:5173

FACEBOOK_APP_ID=1624704349259176
FACEBOOK_APP_SECRET=$FacebookSecret
FACEBOOK_REDIRECT_URI=http://localhost:8000/auth/facebook/callback
"@ | Set-Content -Path $EnvFile -Encoding UTF8

    Write-Host ""
    Write-Host ".env criado com sucesso!" -ForegroundColor Green
}
else {
    Write-Host ".env ja existe. Nenhuma alteracao sera feita." -ForegroundColor Green
}

# ========================================
# BANCO
# ========================================

Write-Host "[5/7] Verificando PostgreSQL..." -ForegroundColor Yellow

$container = docker ps --filter "name=entregafood-db" --format "{{.Names}}"

if ($container -ne "entregafood-db") {

    Write-Host "PostgreSQL nao esta rodando." -ForegroundColor Yellow
    Write-Host "Tentando iniciar pelo Docker Compose..." -ForegroundColor Yellow

    docker compose up -d

    Start-Sleep -Seconds 3

} else {
    Write-Host "PostgreSQL ja esta rodando." -ForegroundColor Green
}

# ========================================
# DEPENDENCIAS BACK
# ========================================

Write-Host "[6/7] Preparando Back-end..." -ForegroundColor Yellow

Set-Location $BackDir

if (Test-Path "requirements.txt") {
    python -m pip install -r requirements.txt
}

# ========================================
# DEPENDENCIAS FRONT
# ========================================

if (-not (Test-Path $FrontDir)) {
    throw "Pasta do Front nao encontrada: $FrontDir"
}

Write-Host "Preparando Front-end..." -ForegroundColor Yellow

Set-Location $FrontDir

if (-not (Test-Path "node_modules")) {
    npm.cmd install
}

# ========================================
# INICIAR SERVIDORES
# ========================================

Write-Host "[7/7] Iniciando Back e Front..." -ForegroundColor Yellow

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$BackDir'; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
)

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$FrontDir'; npm.cmd run dev"
)

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "       ENTREGAFOOD ESTA INICIANDO" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Back : http://localhost:8000" -ForegroundColor Cyan
Write-Host "Docs : http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Front: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "Abra o Front no navegador." -ForegroundColor Green
Write-Host ""