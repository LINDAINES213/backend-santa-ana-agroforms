param(
  [Parameter(Mandatory=$true)] [string]$DB_URL,
  [Parameter(Mandatory=$false)] [string]$OutFile = "backup.dump.enc"
)

function Fail($m){ Write-Error $m; exit 1 }

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) { Fail "pg_dump no está en PATH" }
if (-not (Get-Command openssl -ErrorAction SilentlyContinue)) { Fail "openssl no está en PATH" }

$plain = [System.IO.Path]::GetTempFileName()

# Dump en formato personalizado
pg_dump $DB_URL -Fc -f $plain
if ($LASTEXITCODE -ne 0) { Fail "pg_dump falló" }

# Cifrar con AES-256-GCM + PBKDF2 (con iteraciones altas)
# Passphrase de forma interactiva
openssl enc -aes-256-gcm -salt -pbkdf2 -iter 250000 -in $plain -out $OutFile
if ($LASTEXITCODE -ne 0) {
  Remove-Item $plain -Force
  Fail "openssl enc falló"
}

Remove-Item $plain -Force
Write-Host "OK: backup cifrado creado -> $OutFile"
