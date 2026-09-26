# 간맨틀 DB 논리 백업/새 DB 복원. Windows PowerShell에서 실행합니다.
param(
    [ValidateSet('backup','restore')][string]$Action = 'backup',
    [string]$File,
    [string]$Database
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Docker { if ($LASTEXITCODE -ne 0) { throw 'Docker 명령이 실패했습니다. 기존 DB는 삭제하지 않았습니다.' } }
if ($Action -eq 'backup') {
    if (-not $File) { $File = "backups/ganmantle-$(Get-Date -Format yyyyMMdd-HHmmss).dump" }
    if (Test-Path -LiteralPath $File) { throw '같은 이름의 백업이 있습니다. 다른 파일 이름을 사용하세요.' }
    $destination = [IO.Path]::GetFullPath($File)
    New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
    $remote = '/tmp/ganmantle-' + [guid]::NewGuid().ToString('N') + '.dump'
    docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file="$1"' sh $remote
    Check-Docker
    docker compose cp "db:$remote" $destination
    Check-Docker
    docker compose exec -T db rm -- $remote
    Check-Docker
    Write-Output "백업 완료: $destination"
} else {
    if (-not $File -or -not (Test-Path -LiteralPath $File -PathType Leaf)) { throw '복원할 -File 경로가 필요합니다.' }
    if ($Database -notmatch '^ganmantle_restore_[a-z0-9_]+$') { throw '-Database 이름은 ganmantle_restore_ 로 시작하고 영문 소문자/숫자/밑줄만 사용하세요.' }
    $remote = '/tmp/ganmantle-' + [guid]::NewGuid().ToString('N') + '.dump'
    # 이미 있는 DB면 createdb가 실패하므로 덮어쓰지 않습니다.
    docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh $Database
    Check-Docker
    docker compose cp $File "db:$remote"
    Check-Docker
    docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" --dbname="$1" --exit-on-error --no-owner --no-acl "$2"' sh $Database $remote
    Check-Docker
    # SQL을 표준 입력으로 보내 Windows PowerShell의 중첩 따옴표 해석을 피합니다.
    $query = 'SELECT current_database(); SELECT count(*) AS users FROM users; SELECT count(*) AS games FROM games; SELECT count(*) AS guesses FROM guesses; SELECT filename FROM schema_migrations;'
    $query | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1' sh $Database
    Check-Docker
    docker compose exec -T db rm -- $remote
    Check-Docker
    Write-Output "새 DB로 복원 완료: $Database. 기존 DB와 비교한 뒤 .env의 POSTGRES_DB를 변경하세요."
}