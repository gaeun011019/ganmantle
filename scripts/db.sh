#!/bin/sh
# 간맨틀 DB 논리 백업/새 DB 복원. Mac/Linux에서 sh scripts/db.sh 로 실행합니다.
set -eu
cd "$(dirname "$0")/.."
action=${1:-backup}
file=${2:-backups/ganmantle-$(date +%Y%m%d-%H%M%S).dump}
remote=/tmp/ganmantle-$(date +%s)-$$.dump
case "$action" in
  backup)
    test ! -e "$file" || { echo '같은 이름의 백업이 있습니다.'; exit 1; }
    mkdir -p "$(dirname "$file")"
    docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file="$1"' sh "$remote"
    docker compose cp "db:$remote" "$file"
    docker compose exec -T db rm -- "$remote"
    echo "백업 완료: $file"
    ;;
  restore)
    database=${3:?새 DB 이름 ganmantle_restore_이름 필요}
    case "$database" in ganmantle_restore_?*) ;; *) echo '새 DB 이름은 ganmantle_restore_로 시작해야 합니다.'; exit 1;; esac
    case "$database" in *[!a-z0-9_]*) echo 'DB 이름은 영문 소문자/숫자/밑줄만 가능합니다.'; exit 1;; esac
    test -f "$file"
    docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$database"
    docker compose cp "$file" "db:$remote"
    docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" --dbname="$1" --exit-on-error --no-owner --no-acl "$2"' sh "$database" "$remote"
    docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -c "SELECT current_database(); SELECT count(*) AS users FROM users; SELECT count(*) AS games FROM games; SELECT count(*) AS guesses FROM guesses; SELECT filename FROM schema_migrations;"' sh "$database"
    docker compose exec -T db rm -- "$remote"
    echo "새 DB로 복원 완료: $database. 기존 DB와 비교한 뒤 .env의 POSTGRES_DB를 변경하세요."
    ;;
  *) echo '사용법: sh scripts/db.sh backup [파일] 또는 restore 파일 ganmantle_restore_이름'; exit 1;;
esac
