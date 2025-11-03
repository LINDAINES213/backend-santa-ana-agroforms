param(
  [Parameter(Mandatory=$true)] [string]$EncryptedFile,
  [Parameter(Mandatory=$false)] [string]$Passphrase
)

function Fail($m){ Write-Error $m; exit 1 }

if (-not (Test-Path $EncryptedFile)) { Fail "No existe: $EncryptedFile" }
if (-not (Get-Command openssl -ErrorAction SilentlyContinue)) { Fail "openssl no está en PATH" }
if (-not (Get-Command pg_restore -ErrorAction SilentlyContinue)) { Fail "pg_restore no está en PATH" }

$hash = (Get-FileHash $EncryptedFile -Algorithm SHA256).Hash
Write-Host "SHA256($EncryptedFile) = $hash"

$tmp = [System.IO.Path]::GetTempFileName()
try {
  $args = "enc -d -aes-256-gcm -pbkdf2 -iter 250000 -in `"$EncryptedFile`" -out `"$tmp`""
  if ($Passphrase) {
    $secure = ConvertTo-SecureString $Passphrase -AsPlainText -Force
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $p = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
    $proc = Start-Process -FilePath openssl -ArgumentList $args -NoNewWindow -PassThru -RedirectStandardInput Pipe -RedirectStandardError Pipe
    $proc.StandardInput.WriteLine($p)
    $proc.StandardInput.Close()
    $proc.WaitForExit()
    if ($proc.ExitCode -ne 0) { Fail "Desencriptación falló (clave o archivo). $($proc.StandardError.ReadToEnd())" }
  } else {
    & openssl enc -d -aes-256-gcm -pbkdf2 -iter 250000 -in $EncryptedFile -out $tmp
    if ($LASTEXITCODE -ne 0) { Fail "Desencriptación falló (clave o archivo)." }
  }

  $list = & pg_restore -l $tmp 2>&1
  if ($LASTEXITCODE -ne 0) { Fail "pg_restore -l falló. Dump inválido.`n$list" }

  Write-Host "OK: desencripta y es un dump válido:"
  $list | Select-Object -First 10 | ForEach-Object { Write-Host $_ }
}
finally {
  if (Test-Path $tmp) { Remove-Item $tmp -Force }
}
