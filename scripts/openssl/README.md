# Backups cifrados
- Requiere `pg_dump` y `openssl` en PATH.
- Ejemplo:
  powershell -File scripts/openssl/backup_encrypt.ps1 -DB_URL "postgres://user:pass@host:5432/db" -OUT "dump-YYYYmmdd.dump.enc"
- Para descifrar:
  openssl enc -d -aes-256-gcm -pbkdf2 -iter 250000 -in dump.dump.enc -out dump.dump
