<#
.SYNOPSIS
    Ponto Eletronico - atalhos de desenvolvimento no Windows.

.DESCRIPTION
    Equivalente PowerShell do Makefile. Os dois arquivos expoem os MESMOS
    alvos e devem ser alterados juntos: desenvolvemos em Windows e
    executamos em Linux, entao os dois caminhos precisam funcionar.

.EXAMPLE
    .\tasks.ps1                      # lista os alvos
    .\tasks.ps1 up                   # sobe a stack local
    .\tasks.ps1 logs -Servico api    # segue os logs da api
    .\tasks.ps1 migration -Mensagem "cria tabela marcacoes"
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(
        'help', 'up', 'down', 'restart', 'logs', 'ps',
        'migrate', 'migration', 'seed', 'psql', 'redis', 'shell',
        'test', 'test-web', 'lint', 'lint-web', 'typecheck', 'fmt',
        'validate', 'build', 'env', 'keys', 'bootstrap', 'clean', 'nuke'
    )]
    [string]$Alvo = 'help',

    # Servico alvo em logs/shell (equivale ao s= do Makefile).
    [string]$Servico,

    # Mensagem da migration (equivale ao m= do Makefile).
    [string]$Mensagem
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------
$Raiz       = $PSScriptRoot
$Infra      = Join-Path $Raiz 'infra'
$EnvFile    = Join-Path $Infra '.env'
$EnvExemplo = Join-Path $Infra '.env.example'
$KeysDir    = Join-Path $Infra 'keys'
$WebDir     = Join-Path $Raiz 'apps\web'

$ComposePrd = @(
    'compose',
    '--env-file', $EnvFile,
    '-f', (Join-Path $Infra 'docker-compose.yml')
)
$ComposeDev = $ComposePrd + @('-f', (Join-Path $Infra 'docker-compose.dev.yml'))

# -----------------------------------------------------------------------------
# Utilitarios
# -----------------------------------------------------------------------------
function Write-Passo {
    param([string]$Texto)
    Write-Host "==> $Texto" -ForegroundColor Cyan
}

function Invoke-Externo {
    <#  Executa um comando externo e propaga o codigo de saida.
        PowerShell 5.1 nao aborta sozinho quando um .exe retorna != 0.  #>
    param(
        [Parameter(Mandatory)][string]$Comando,
        [string[]]$Argumentos = @()
    )
    & $Comando @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw "Comando falhou (codigo $LASTEXITCODE): $Comando $($Argumentos -join ' ')"
    }
}

function Invoke-Compose {
    param([string[]]$Argumentos, [switch]$Producao)
    $base = if ($Producao) { $ComposePrd } else { $ComposeDev }
    Invoke-Externo -Comando 'docker' -Argumentos ($base + $Argumentos)
}

function Test-Ferramenta {
    param([string]$Nome, [string]$Dica)
    if (-not (Get-Command $Nome -ErrorAction SilentlyContinue)) {
        throw "'$Nome' nao encontrado no PATH. $Dica"
    }
}

# -----------------------------------------------------------------------------
# Alvos
# -----------------------------------------------------------------------------
function Alvo-Help {
    Write-Host ''
    Write-Host '  Ponto Eletronico - alvos disponiveis' -ForegroundColor Green
    Write-Host ''
    $tabela = [ordered]@{
        'up'        = 'Sobe a stack local (dev: portas publicadas, hot reload)'
        'down'      = 'Derruba a stack (preserva volumes)'
        'restart'   = 'Reinicia todos os servicos'
        'logs'      = 'Segue os logs (-Servico api para um servico)'
        'ps'        = 'Estado e saude dos containers'
        'migrate'   = 'Aplica as migrations Alembic ate head'
        'migration' = 'Cria migration autogerada (-Mensagem "descricao")'
        'seed'      = 'Carrega dados sinteticos de desenvolvimento'
        'psql'      = 'Abre psql no banco da stack'
        'redis'     = 'Abre redis-cli na stack'
        'shell'     = 'Shell no container (-Servico worker)'
        'test'      = 'Testes Python (pytest com cobertura)'
        'test-web'  = 'Testes do web'
        'lint'      = 'Lint Python (ruff)'
        'lint-web'  = 'Lint do web (eslint)'
        'typecheck' = 'Tipos: mypy (Python) e tsc (web)'
        'fmt'       = 'Formata o codigo (ruff + prettier)'
        'validate'  = 'Valida YAML da infra, compose e contrato OpenAPI'
        'build'     = 'Constroi as imagens Docker'
        'env'       = 'Cria infra\.env a partir do exemplo'
        'keys'      = 'Gera o par de chaves JWT RS256 em infra\keys'
        'bootstrap' = 'Prepara o ambiente do zero'
        'clean'     = 'Remove caches de build e de ferramentas'
        'nuke'      = 'Derruba a stack E APAGA OS VOLUMES'
    }
    foreach ($k in $tabela.Keys) {
        Write-Host ('  {0,-12}' -f $k) -ForegroundColor Cyan -NoNewline
        Write-Host $tabela[$k]
    }
    Write-Host ''
    Write-Host '  Equivalente Linux/macOS: make <alvo>' -ForegroundColor DarkGray
    Write-Host ''
}

function Alvo-Env {
    if (-not (Test-Path $EnvFile)) {
        Copy-Item $EnvExemplo $EnvFile
        Write-Passo "Criado $EnvFile a partir do exemplo. Revise os valores."
    }
}

function Alvo-Up {
    Alvo-Env
    Invoke-Compose @('up', '-d', '--remove-orphans')
    Write-Host ''
    Write-Host '  web        http://localhost:3000'
    Write-Host '  api        http://localhost:8000'
    Write-Host '  docs       http://localhost:8000/docs'
    Write-Host '  device-gw  http://localhost:8001'
    Write-Host '  minio      http://localhost:9001'
    Write-Host ''
}

function Alvo-Down    { Invoke-Compose @('down', '--remove-orphans') }
function Alvo-Restart { Invoke-Compose @('restart') }
function Alvo-Ps      { Invoke-Compose @('ps') }

function Alvo-Logs {
    # Nao usar $args: e variavel automatica do PowerShell.
    $argumentos = @('logs', '-f', '--tail=200')
    if ($Servico) { $argumentos += $Servico }
    Invoke-Compose $argumentos
}

function Alvo-Migrate {
    Invoke-Compose @('exec', 'api', 'alembic', 'upgrade', 'head')
}

function Alvo-Migration {
    if (-not $Mensagem) {
        throw 'Uso: .\tasks.ps1 migration -Mensagem "descricao da mudanca"'
    }
    Invoke-Compose @('exec', 'api', 'alembic', 'revision', '--autogenerate', '-m', $Mensagem)
}

function Alvo-Seed  { Invoke-Compose @('exec', 'api', 'python', '-m', 'app.scripts.seed') }
function Alvo-Psql  { Invoke-Compose @('exec', 'postgres', 'sh', '-c', 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"') }
function Alvo-Redis { Invoke-Compose @('exec', 'redis', 'sh', '-c', 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning') }

function Alvo-Shell {
    $alvo = if ($Servico) { $Servico } else { 'api' }
    Invoke-Compose @('exec', $alvo, '/bin/sh')
}

function Alvo-Test {
    Invoke-Compose @('exec', '-T', 'api', 'pytest', '-q', '--cov', '--cov-report=term-missing')
}

function Alvo-TestWeb {
    Push-Location $WebDir
    try { Invoke-Externo -Comando 'pnpm' -Argumentos @('test') } finally { Pop-Location }
}

function Alvo-Lint {
    Test-Ferramenta 'ruff' 'Instale com: pip install ruff'
    Invoke-Externo -Comando 'ruff' -Argumentos @('check', 'apps', 'packages', 'tests')
    Invoke-Externo -Comando 'ruff' -Argumentos @('format', '--check', 'apps', 'packages', 'tests')
}

function Alvo-LintWeb {
    Push-Location $WebDir
    try { Invoke-Externo -Comando 'pnpm' -Argumentos @('lint') } finally { Pop-Location }
}

function Alvo-Typecheck {
    Test-Ferramenta 'mypy' 'Instale com: pip install mypy'
    Invoke-Externo -Comando 'mypy' -Argumentos @('apps', 'packages')
    Push-Location $WebDir
    try { Invoke-Externo -Comando 'pnpm' -Argumentos @('exec', 'tsc', '--noEmit') } finally { Pop-Location }
}

function Alvo-Fmt {
    Test-Ferramenta 'ruff' 'Instale com: pip install ruff'
    Invoke-Externo -Comando 'ruff' -Argumentos @('format', 'apps', 'packages', 'tests')
    Invoke-Externo -Comando 'ruff' -Argumentos @('check', '--fix', 'apps', 'packages', 'tests')
    Push-Location $WebDir
    try { Invoke-Externo -Comando 'pnpm' -Argumentos @('exec', 'prettier', '--write', '.') } finally { Pop-Location }
}

function Alvo-Validate {
    Write-Passo 'Sintaxe YAML dos arquivos de infra e CI'
    $script = @'
import pathlib, sys, yaml
erros = 0
alvos = []
for pasta in ("infra", ".github"):
    p = pathlib.Path(pasta)
    if p.exists():
        alvos += list(p.rglob("*.yml")) + list(p.rglob("*.yaml"))
for arq in sorted(set(alvos)):
    try:
        list(yaml.safe_load_all(arq.read_text(encoding="utf-8")))
        print("ok    %s" % arq)
    except Exception as exc:
        erros += 1
        print("FALHA %s: %s" % (arq, exc), file=sys.stderr)
print("%d arquivo(s), %d falha(s)" % (len(set(alvos)), erros))
sys.exit(1 if erros else 0)
'@
    $tmp = Join-Path $env:TEMP 'ponto-valida-yaml.py'
    # ascii de proposito: o script e ASCII puro e o BOM do utf8 do PS 5.1
    # so atrapalharia ferramentas a jusante.
    Set-Content -Path $tmp -Value $script -Encoding ascii
    Invoke-Externo -Comando 'python' -Argumentos @($tmp)

    Write-Passo 'docker compose config (producao)'
    Invoke-Compose @('config', '--quiet') -Producao
    Write-Passo 'docker compose config (dev)'
    Invoke-Compose @('config', '--quiet')

    $openapi = Join-Path $Raiz 'packages\contracts\openapi.yaml'
    if (Test-Path $openapi) {
        Write-Passo 'spectral lint no openapi.yaml'
        Invoke-Externo -Comando 'npx' -Argumentos @(
            '--yes', '@stoplight/spectral-cli', 'lint', $openapi, '--fail-severity=warn'
        )
    }
    else {
        Write-Host 'openapi.yaml ainda nao existe; validacao de contrato pulada.' -ForegroundColor Yellow
    }
}

function Alvo-Build { Invoke-Compose @('build') -Producao }

function Alvo-Keys {
    Test-Ferramenta 'openssl' 'Vem com o Git for Windows (C:\Program Files\Git\usr\bin).'
    if (-not (Test-Path $KeysDir)) { New-Item -ItemType Directory -Path $KeysDir | Out-Null }
    $priv = Join-Path $KeysDir 'private.pem'
    $pub  = Join-Path $KeysDir 'public.pem'
    if (Test-Path $priv) {
        Write-Host "Chaves ja existem em $KeysDir. Apague antes de regerar." -ForegroundColor Yellow
        return
    }
    Invoke-Externo -Comando 'openssl' -Argumentos @(
        'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:4096', '-out', $priv
    )
    Invoke-Externo -Comando 'openssl' -Argumentos @('rsa', '-pubout', '-in', $priv, '-out', $pub)
    Write-Passo "Chaves geradas em $KeysDir (fora do git)."
}

function Alvo-Bootstrap {
    Alvo-Env
    Alvo-Keys
    Write-Passo 'Construindo imagens'
    Invoke-Compose @('build')
    Write-Passo 'Subindo a stack'
    Invoke-Compose @('up', '-d')
    Write-Passo 'Aguardando a api ficar healthy'
    $limite = (Get-Date).AddMinutes(5)
    $argsPs = $ComposeDev + @('ps', '-q', 'api')
    $saude = 'starting'
    do {
        Start-Sleep -Seconds 3
        $id = (& docker @argsPs) | Select-Object -First 1
        $saude = if ($id) { & docker inspect -f '{{.State.Health.Status}}' $id } else { 'starting' }
        Write-Host "  api: $saude"
    } while ($saude -ne 'healthy' -and (Get-Date) -lt $limite)
    if ($saude -ne 'healthy') { throw 'A api nao ficou healthy no tempo esperado.' }
    Alvo-Migrate
    Write-Passo 'Ambiente pronto. .\tasks.ps1 logs para acompanhar.'
}

function Alvo-Clean {
    $caminhos = @(
        '.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov',
        '.coverage', 'coverage.xml', 'apps\web\.next', 'apps\web\.turbo'
    )
    foreach ($c in $caminhos) {
        $p = Join-Path $Raiz $c
        if (Test-Path $p) {
            Remove-Item -Recurse -Force $p -Confirm:$false
            Write-Host "  removido $c"
        }
    }
    Get-ChildItem -Path $Raiz -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -Recurse -Force $_.FullName -Confirm:$false }
    Write-Passo 'Caches removidos.'
}

function Alvo-Nuke {
    Write-Host 'Isso apaga o banco, o Redis e o MinIO locais.' -ForegroundColor Red
    $r = Read-Host 'Digite APAGAR para confirmar'
    if ($r -ne 'APAGAR') { Write-Host 'Cancelado.'; return }
    Invoke-Compose @('down', '-v', '--remove-orphans')
}

# -----------------------------------------------------------------------------
# Despacho
# -----------------------------------------------------------------------------
switch ($Alvo) {
    'help'      { Alvo-Help }
    'up'        { Alvo-Up }
    'down'      { Alvo-Down }
    'restart'   { Alvo-Restart }
    'logs'      { Alvo-Logs }
    'ps'        { Alvo-Ps }
    'migrate'   { Alvo-Migrate }
    'migration' { Alvo-Migration }
    'seed'      { Alvo-Seed }
    'psql'      { Alvo-Psql }
    'redis'     { Alvo-Redis }
    'shell'     { Alvo-Shell }
    'test'      { Alvo-Test }
    'test-web'  { Alvo-TestWeb }
    'lint'      { Alvo-Lint }
    'lint-web'  { Alvo-LintWeb }
    'typecheck' { Alvo-Typecheck }
    'fmt'       { Alvo-Fmt }
    'validate'  { Alvo-Validate }
    'build'     { Alvo-Build }
    'env'       { Alvo-Env }
    'keys'      { Alvo-Keys }
    'bootstrap' { Alvo-Bootstrap }
    'clean'     { Alvo-Clean }
    'nuke'      { Alvo-Nuke }
    default     { Alvo-Help }
}
