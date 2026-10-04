#!/bin/sh
# Mac/Linux 실행과 관리. 프로젝트 밖에서도 sh 경로/scripts/manage.sh 로 실행할 수 있습니다.
set -eu

usage() {
  cat <<'EOF'
사용법: sh scripts/manage.sh 명령 [인자]

  help                         이 안내 보기 (Docker 불필요)
  setup                        최초 설정·이미지 빌드·모델 준비·앱 시작
  start                        준비된 앱과 DB 시작, 정상 상태까지 대기
  stop                         앱과 DB 정지 (데이터 보존)
  status                       컨테이너 상태 확인
  logs [app|db]                최근 로그 80줄 확인 (기본 app)
  update                       이미지 다시 빌드하고 앱에 반영
  backup [파일]                DB 백업 (기본 backups/날짜.dump)
  restore 파일 새_DB명          백업을 ganmantle_restore_로 시작하는 새 DB에 복원

파일 경로는 프로젝트 폴더 기준입니다. 공백이 있으면 따옴표로 감싸세요.
update 전에는 backup을 실행하세요. restore는 사용 중인 DB를 자동으로 바꾸지 않습니다.
EOF
}

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

invalid_arguments() {
  usage >&2
  fail '명령과 인자를 확인하세요.'
}

cd "$(dirname "$0")/.." || fail '프로젝트 폴더를 찾지 못했습니다.'

action=${1-help}
if [ "$#" -gt 0 ]; then
  shift
fi

# 인자 오류는 Docker 확인이나 파일 생성 전에 처리합니다.
case "$action" in
  help|setup|start|stop|status|update)
    [ "$#" -eq 0 ] || invalid_arguments
    ;;
  logs)
    [ "$#" -le 1 ] || invalid_arguments
    service=${1-app}
    case "$service" in
      app|db) ;;
      *) invalid_arguments ;;
    esac
    ;;
  backup)
    [ "$#" -le 1 ] || invalid_arguments
    file=${1-backups/ganmantle-$(date +%Y%m%d-%H%M%S).dump}
    [ -n "$file" ] || invalid_arguments
    case "$file" in
      -*) fail '파일 이름이 -로 시작하면 앞에 ./를 붙이세요.' ;;
    esac
    [ ! -e "$file" ] || fail '같은 이름의 백업이 있습니다.'
    ;;
  restore)
    [ "$#" -eq 2 ] || invalid_arguments
    file=$1
    database=$2
    case "$file" in
      -*) fail '파일 이름이 -로 시작하면 앞에 ./를 붙이세요.' ;;
    esac
    case "$database" in
      ganmantle_restore_?*) ;;
      *) fail '새 DB 이름은 ganmantle_restore_로 시작해야 합니다.' ;;
    esac
    case "$database" in
      *[!a-z0-9_]*) fail 'DB 이름은 영문 소문자·숫자·밑줄만 가능합니다.' ;;
    esac
    [ "${#database}" -le 63 ] || fail 'DB 이름은 63자 이내로 입력하세요.'
    [ -f "$file" ] || fail '복원할 백업 파일을 찾지 못했습니다.'
    ;;
  *) invalid_arguments ;;
esac

if [ "$action" = help ]; then
  usage
  exit 0
fi

command -v docker >/dev/null 2>&1 || fail 'Docker Desktop을 설치하고 실행하세요.'
docker info >/dev/null 2>&1 || fail 'Docker Desktop을 실행한 뒤 다시 시도하세요.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose를 사용할 수 없습니다.'

if [ "$action" != setup ] && [ ! -f .env ]; then
  fail '.env가 없습니다. 먼저 sh scripts/manage.sh setup을 실행하세요.'
fi

run_docker() {
  docker "$@" || fail 'Docker 작업에 실패했습니다. 위 오류를 확인하세요.'
}

start_app() {
  run_docker compose up -d --wait --wait-timeout 600
  printf '%s\n' '앱과 DB가 정상 상태입니다. 접속 주소는 README.md와 .env 설정을 확인하세요.'
}

case "$action" in
  setup)
    python_image='python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7'
    printf '%s\n' '기존 .env는 보존합니다. 최초 모델 준비에는 다운로드와 처리 시간이 필요합니다.'
    run_docker run --rm --volume "$PWD:/work" --workdir /work \
      "$python_image" python scripts/setup_env.py
    run_docker compose build app
    run_docker compose run --rm --no-deps --user 0:0 \
      --volume ganmantle-v1_model_data:/model-work:rw \
      app python scripts/prepare_model.py --directory /model-work/fasttext-ko
    run_docker compose run --rm --no-deps --user 0:0 \
      --volume ganmantle-v1_model_data:/model-work:rw \
      app python scripts/prepare_word_ranks.py --directory /model-work/fasttext-ko
    start_app
    ;;
  start)
    start_app
    ;;
  stop)
    run_docker compose stop
    printf '%s\n' '앱과 DB를 정지했습니다. 데이터와 모델은 보존했습니다.'
    ;;
  status)
    run_docker compose ps
    ;;
  logs)
    run_docker compose logs --tail 80 "$service"
    ;;
  update)
    printf '%s\n' '이미지를 다시 빌드합니다. DB 백업은 backup 명령으로 할 수 있습니다.'
    run_docker compose build app
    start_app
    ;;
  backup)
    sh scripts/db.sh backup "$file"
    ;;
  restore)
    sh scripts/db.sh restore "$file" "$database"
    ;;
esac
