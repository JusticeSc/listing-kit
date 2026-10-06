#!/usr/bin/env bash
# Amazon Listing Kit — 发布事务脚本（修复旧容器提前清理的回退缺口）。
#
# 背景：旧流水线在容器 healthy 后、外部 HTTPS 检查前就删除 previous 容器，
# TLS/静态资源/页面失败时已无可恢复的上一版本。本脚本把一次发布做成完整事务：
# previous 应用容器与 Caddy 配置备份至少保留到容器健康、受信 HTTPS、静态资源
# （首页外壳与样式/脚本字节）全部验收结束；任一必要失败都回退到上一已知可用
# 状态并核对实际可用性；只有全部验收通过才清理旧版本与备份。约定页面主链
# （实际启动/状态就绪/新建后刷新仍在/零错误）由事务外的 acceptance 步骤覆盖，
# finalize 前任一失败同样走 rollback 恢复。
#
# 子命令（同一参数形状，便于多次 SSH 调用共用；事务身份经服务器配置文件跨会话保持）：
#   deploy   <image> <name> <port> <context> <public_ip> <https_port>
#   finalize <image> <name> <port> <context> <public_ip> <https_port>
#   rollback <image> <name> <port> <context> <public_ip> <https_port> [reason]
#
# 退出码：0 成功；1 已回退/拒绝（发布失败但系统状态明确，job 保持红）；
# 2 用法错误；3 unrecovered_failed_release（回退失败，系统未恢复到已知可用状态）；
# 4 finalize 收尾失败（新版本健康但旧版本/备份/事务清理不完，或无有效开放事务；
# 绝不自动回滚，需人工清理；工作流 rollback 门只看 exit 1 的重验证失败）。
# 日志只含镜像名/容器名/端口与阶段，不打印任何密钥。
set -Eeuo pipefail

RELEASE_DIR="${HOME}/.config/amz-listing-kit"
TRANSACTION_FILE="${RELEASE_DIR}/deploy-transaction.env"
INSTALL_PATH="${RELEASE_DIR}/release-transaction.sh"

EXIT_OK=0
EXIT_FAILED=1
EXIT_USAGE=2
EXIT_UNRECOVERED=3
EXIT_FINALIZE=4

# 本事务读写的过程全局量（deploy 内设置；rollback 按事务文件重建）。
G_NAME=""
G_IMAGE=""
G_PREVIOUS=""
G_PREVIOUS_EXISTED="false"
G_PREVIOUS_IMAGE="none"
G_NEW_STARTED="false"
G_TLS_NAME=""
G_TLS_EXISTED="false"
G_CADDYFILE=""
G_CADDY_EXISTED="false"
G_BACKUP=""
G_BACKED_UP="false"
G_INSTALLED_NEW="false"
G_INSTALL_INTENT="false"
G_PUBLIC_IP=""
G_HTTPS_PORT=""
log() {
  printf '%s release-transaction %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

usage() {
  cat >&2 <<'EOF'
用法：
  release-transaction.sh deploy   <image> <name> <port> <context> <public_ip> <https_port>
  release-transaction.sh finalize <image> <name> <port> <context> <public_ip> <https_port>
  release-transaction.sh rollback <image> <name> <port> <context> <public_ip> <https_port> [reason]
EOF
  exit "$EXIT_USAGE"
}

check_context() {
  case "$1" in
    /tmp/amz-listing-kit-[0-9a-f]*) ;;
    *) log "refusing unexpected build context: $1"; exit "$EXIT_USAGE" ;;
  esac
}

container_exists() { docker container inspect "$1" >/dev/null 2>&1; }
container_image() { docker inspect --format '{{.Config.Image}}' "$1" 2>/dev/null || printf ''; }

container_running() {
  local state=""
  if ! state="$(docker inspect --format '{{.State.Running}}' "$1" 2>/dev/null)"; then
    return 1
  fi
  [ "$state" = "true" ]
}

container_health() {
  local status=""
  if ! status="$(docker inspect --format '{{.State.Health.Status}}' "$1" 2>/dev/null)"; then
    printf 'missing'
    return 0
  fi
  printf '%s' "$status"
}

wait_healthy() {
  local name="$1" tries="${2:-30}" attempt status
  for attempt in $(seq 1 "$tries"); do
    status="$(container_health "$name")"
    if [ "$status" = "healthy" ]; then return 0; fi
    if [ "$status" = "unhealthy" ]; then return 1; fi
    sleep 2
  done
  return 1
}

wait_https() {
  local url="$1" tries="${2:-20}" attempt
  for attempt in $(seq 1 "$tries"); do
    if curl -fsS --max-time 8 "$url" >/dev/null 2>&1; then return 0; fi
    sleep 3
  done
  return 1
}

check_static() {
  # 与 finalize/acceptance 同判据：首页外壳标记与样式/脚本字节。
  local public_ip="$1" https_port="$2" html=""
  # 完整读取再判外壳；grep -q 提前退出在 pipefail 下会把正常大页面变成 curl 23。
  if ! html="$(curl -fsS --max-time 8 "https://${public_ip}:${https_port}/" 2>/dev/null)"; then
    return 1
  fi
  case "$html" in
    *'id="project-list"'*) ;;
    *) return 1 ;;
  esac
  if ! curl -fsS --max-time 8 "https://${public_ip}:${https_port}/styles.css" >/dev/null 2>&1; then
    return 1
  fi
  if ! curl -fsS --max-time 8 "https://${public_ip}:${https_port}/entry.js" >/dev/null 2>&1; then
    return 1
  fi
  if ! curl -fsS --max-time 8 "https://${public_ip}:${https_port}/app.js" >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

container_state_dump() {
  # 诊断只含容器名/状态/镜像，不含任何密钥与环境内容。
  if ! docker ps -a --filter "name=$1" --format '{{.Names}} status={{.Status}} image={{.Image}}' 2>/dev/null; then
    log "cannot list containers"
  fi
}

write_transaction() {
  # $1 image $2 name $3 previous $4 previous_existed $5 previous_image $6 tls_name
  # $7 tls_existed $8 caddyfile $9 caddyfile_existed ${10} backup ${11} backed_up ${12} installed_new
  # ${13} phase（可选）：baseline（变异前）/ parked（旧版已停放）/ new_healthy / tls_converged /
  # https_ok（deploy 完成，待 acceptance/finalize）。身份字段一律单引号包裹，
  # 允许镜像名里的 : / . - 等字符；调用方传参必须来自工作流固定变量，不拼接用户输入。
  # ${14} new_started（可选）：serving 名下是否已启动本次新容器（true/false，缺省 false）。
  # ${15} install_intent（可选）：是否已记录本次 Caddy 首次安装意图（true/false，缺省 false）。
  install -d -m 700 "$RELEASE_DIR"
  local tmp="" phase="https_ok" new_started="false" install_intent="false"
  if [ "$#" -ge 13 ]; then phase="${13}"; fi
  if [ "$#" -ge 14 ]; then new_started="${14}"; fi
  if [ "$#" -ge 15 ]; then install_intent="${15}"; fi
  if ! tmp="$(mktemp)"; then log "cannot create temp file"; return 1; fi
  {
    printf "SCHEMA='release-transaction/v1'\n"
    printf "IMAGE='%s'\n" "$1"
    printf "NAME='%s'\n" "$2"
    printf "PREVIOUS='%s'\n" "$3"
    printf "PREVIOUS_EXISTED='%s'\n" "$4"
    printf "PREVIOUS_IMAGE='%s'\n" "$5"
    printf "NEW_STARTED='%s'\n" "$new_started"
    printf "TLS_NAME='%s'\n" "$6"
    printf "TLS_EXISTED='%s'\n" "$7"
    printf "CADDYFILE='%s'\n" "$8"
    printf "CADDYFILE_EXISTED='%s'\n" "$9"
    printf "BACKUP='%s'\n" "${10}"
    printf "BACKED_UP='%s'\n" "${11}"
    printf "INSTALLED_NEW='%s'\n" "${12}"
    printf "INSTALL_INTENT='%s'\n" "$install_intent"
    printf "PHASE='%s'\n" "$phase"
    printf "CREATED_AT='%s'\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$TRANSACTION_FILE"
}

update_phase() {
  # 幂等推进阶段标记：只在事务文件存在且身份一致时更新，不改变其他身份字段。
  if [ ! -f "$TRANSACTION_FILE" ]; then return 1; fi
  if ! load_transaction; then return 1; fi
  if [ "${NAME:-}" != "$G_NAME" ] || [ "${IMAGE:-}" != "$G_IMAGE" ]; then return 1; fi
  PHASE="$1"
  local tmp=""
  if ! tmp="$(mktemp)"; then return 1; fi
  {
    printf "SCHEMA='release-transaction/v1'\n"
    printf "IMAGE='%s'\n" "${IMAGE:-}"
    printf "NAME='%s'\n" "${NAME:-}"
    printf "PREVIOUS='%s'\n" "${PREVIOUS:-}"
    printf "PREVIOUS_EXISTED='%s'\n" "${PREVIOUS_EXISTED:-false}"
    printf "PREVIOUS_IMAGE='%s'\n" "${PREVIOUS_IMAGE:-none}"
    printf "NEW_STARTED='%s'\n" "${NEW_STARTED:-false}"
    printf "TLS_NAME='%s'\n" "${TLS_NAME:-}"
    printf "TLS_EXISTED='%s'\n" "${TLS_EXISTED:-false}"
    printf "CADDYFILE='%s'\n" "${CADDYFILE:-}"
    printf "CADDYFILE_EXISTED='%s'\n" "${CADDYFILE_EXISTED:-false}"
    printf "BACKUP='%s'\n" "${BACKUP:-}"
    printf "BACKED_UP='%s'\n" "${BACKED_UP:-false}"
    printf "INSTALLED_NEW='%s'\n" "${INSTALLED_NEW:-false}"
    printf "INSTALL_INTENT='%s'\n" "${INSTALL_INTENT:-false}"
    printf "PHASE='%s'\n" "$1"
    printf "CREATED_AT='%s'\n" "${CREATED_AT:-unknown}"
  } > "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$TRANSACTION_FILE"
}

load_transaction() {
  if [ ! -f "$TRANSACTION_FILE" ]; then return 1; fi
  # 本文件只由本脚本写入，值为镜像名/容器名/路径与 true/false，无不可信内容。
  # shellcheck disable=SC1090
  . "$TRANSACTION_FILE"
  return 0
}

restore_app_container() {
  # 把 previous 恢复为 serving 名。0=已恢复且健康；2=首发无 previous；1=恢复失败。
  # $4 new_started：serving 名下是否已启动本次新容器（journal NEW_STARTED）。
  # $5 expected_image：本次新镜像（journal IMAGE；仅 new_started=true 时比对）。
  # 早失败（new_started=false）绝不删除 serving 名下仍在的原服务，只核对健康。
  local name="$1" previous="$2" had_previous="$3" new_started="${4:-false}" expected_image="${5:-}" actual=""
  if [ "$new_started" = "true" ]; then
    if container_exists "$name"; then
      if [ -n "$expected_image" ]; then
        actual="$(container_image "$name")"
        if [ "$actual" != "$expected_image" ]; then
          log "refusing to remove serving ${name}: image ${actual:-unknown} != expected new image ${expected_image}; original may not be parked"
          container_state_dump "$name"
          return 1
        fi
      fi
      log "removing failed new container ${name}"
      if ! docker rm --force "$name" >/dev/null; then
        log "cannot remove failed container ${name}"
        return 1
      fi
    fi
  else
    if container_exists "$name"; then
      if [ "$had_previous" = "true" ] && ! container_exists "$previous"; then
        # previous 已记停放但 serving 名仍被占且 previous 不见：中断过渡无法区分
        # 新旧身份，绝不自动删除 serving 名下容器，必须人工核对。
        log "serving ${name} present but parked previous missing; cannot disambiguate interrupted transition; manual check needed"
        container_state_dump "$name"
        return 1
      fi
      log "early failure before new-container start: original serving ${name} untouched; verifying health"
      if ! wait_healthy "$name" 30; then
        log "original serving ${name} not healthy after early failure"
        return 1
      fi
      log "original serving still healthy: ${name}"
      return 0
    fi
    if [ "$had_previous" = "true" ] && container_exists "$previous"; then
      log "early failure with serving missing but parked previous present; cannot disambiguate interrupted transition; manual check needed"
      container_state_dump "$previous"
      return 1
    fi
    if [ "$had_previous" != "true" ]; then
      log "no previous container to restore (first deploy)"
      return 2
    fi
    log "previous container ${previous} missing and no serving to preserve; cannot restore"
    return 1
  fi
  if [ "$had_previous" != "true" ]; then
    log "no previous container to restore (first deploy)"
    return 2
  fi
  if ! container_exists "$previous"; then
    log "previous container ${previous} missing; cannot restore"
    return 1
  fi
  if [ -n "${G_PREVIOUS_IMAGE:-}" ] && [ "${G_PREVIOUS_IMAGE:-none}" != "none" ] \
    && [ "${G_PREVIOUS_IMAGE:-none}" != "unknown" ]; then
    actual="$(container_image "$previous")"
    if [ "$actual" != "$G_PREVIOUS_IMAGE" ]; then
      log "refusing to restore previous ${previous}: image ${actual:-missing} != parked ${G_PREVIOUS_IMAGE}; not the parked original"
      container_state_dump "$previous"
      return 1
    fi
  fi
  log "restoring previous ${previous} to ${name}"
  if ! docker rename "$previous" "$name" >/dev/null; then
    log "rename ${previous} to ${name} failed"
    return 1
  fi
  if ! docker start "$name" >/dev/null; then
    log "start ${name} failed"
    return 1
  fi
  if ! wait_healthy "$name" 30; then
    log "restored container ${name} not healthy"
    if ! docker logs "$name" 2>&1 | tail -30 >&2; then
      log "no logs from ${name}"
    fi
    return 1
  fi
  log "previous restored and healthy: ${name}"
  return 0
}

restore_tls() {
  # 按事务记录恢复 TLS：备份写回或清除本次新建（含首次安装意图已记但文件未完整落盘的中断残留）。
  local tls_name="$1" tls_existed="$2" caddyfile="$3" caddy_existed="$4"
  local backup="$5" backed_up="$6" installed_new="$7" install_intent="${8:-false}"
  if [ "$backed_up" = "true" ]; then
    if [ ! -f "$backup" ]; then
      log "caddy backup ${backup} missing"
      return 1
    fi
    log "restoring Caddyfile from backup"
    if ! install -m 600 "$backup" "$caddyfile"; then
      log "caddyfile restore failed"
      return 1
    fi
  elif [ "$installed_new" = "true" ] || { [ "$install_intent" = "true" ] && [ "$caddy_existed" = "false" ]; }; then
    log "removing newly installed Caddyfile (no prior config)"
    rm -f -- "$caddyfile"
  elif [ "$caddy_existed" = "false" ]; then
    log "no prior Caddyfile and nothing newly installed; leaving TLS config alone"
  fi
  if [ "$tls_existed" = "true" ]; then
    log "restarting previous TLS container ${tls_name}"
    if container_running "$tls_name"; then
      if ! docker restart "$tls_name" >/dev/null; then
        log "tls restart failed"
        return 1
      fi
    else
      if ! docker start "$tls_name" >/dev/null; then
        log "tls start failed"
        return 1
      fi
    fi
    sleep 2
    if ! container_running "$tls_name"; then
      log "tls container not running after restore"
      return 1
    fi
  else
    if container_exists "$tls_name"; then
      log "removing newly created TLS container ${tls_name}"
      if ! docker rm --force "$tls_name" >/dev/null; then
        log "cannot remove new tls container"
        return 1
      fi
    fi
  fi
  return 0
}

clear_open_transaction() {
  local cleanup_rc=0
  if [ "$G_BACKED_UP" = "true" ] && [ -f "$G_BACKUP" ]; then
    if ! rm -f -- "$G_BACKUP"; then
      log "cannot remove backup ${G_BACKUP} (continuing)"
      cleanup_rc=1
    fi
  fi
  if ! rm -f -- "$TRANSACTION_FILE"; then
    log "cannot remove transaction file (continuing)"
    cleanup_rc=1
  fi
  return "$cleanup_rc"
}

rollback_open_release() {
  # 按全局事务记录做完整回退；成功恢复则 exit 1（发布失败、系统已恢复）,
  # 恢复失败则 exit 3（unrecovered_failed_release）。绝不把失败的回退报成成功。
  local reason="$1" rc=0 trc=0 url=""
  log "rolling back open release: ${reason}"
  restore_app_container "$G_NAME" "$G_PREVIOUS" "$G_PREVIOUS_EXISTED" "${G_NEW_STARTED:-false}" "$G_IMAGE" || rc="$?"
  if [ "$rc" = "2" ]; then
    restore_tls "$G_TLS_NAME" "$G_TLS_EXISTED" "$G_CADDYFILE" "$G_CADDY_EXISTED" \
      "$G_BACKUP" "$G_BACKED_UP" "$G_INSTALLED_NEW" "${G_INSTALL_INTENT:-false}" || trc="$?"
    if [ "$trc" != "0" ]; then
      log "unrecovered_failed_release: ${reason}; first deploy has no previous and TLS cleanup failed"
      container_state_dump "$G_TLS_NAME"
      exit "$EXIT_UNRECOVERED"
    fi
    if ! clear_open_transaction; then
      log "rolled back to empty (no previous existed); leftover backup/transaction needs manual cleanup"
    else
      log "rolled back to empty (no previous existed)"
    fi
    exit "$EXIT_FAILED"
  fi
  if [ "$rc" != "0" ]; then
    log "unrecovered_failed_release: ${reason}; app restore failed"
    container_state_dump "$G_NAME"
    container_state_dump "$G_PREVIOUS"
    exit "$EXIT_UNRECOVERED"
  fi
  # previous 身份在 restore_app_container 内部已删除复用名并重命名，无需在此二次核对。
  restore_tls "$G_TLS_NAME" "$G_TLS_EXISTED" "$G_CADDYFILE" "$G_CADDY_EXISTED" \
    "$G_BACKUP" "$G_BACKED_UP" "$G_INSTALLED_NEW" "${G_INSTALL_INTENT:-false}" || trc="$?"
  if [ "$trc" != "0" ]; then
    log "unrecovered_failed_release: ${reason}; app restored but TLS restore failed"
    container_state_dump "$G_TLS_NAME"
    exit "$EXIT_UNRECOVERED"
  fi
  url="https://${G_PUBLIC_IP}:${G_HTTPS_PORT}/api/health"
  if ! wait_https "$url" 20; then
    log "unrecovered_failed_release: ${reason}; app and TLS restored but ${url} still failing"
    if ! docker logs --tail 40 "$G_TLS_NAME" 2>&1 | tail -20 >&2; then
      log "no tls logs"
    fi
    exit "$EXIT_UNRECOVERED"
  fi
  if ! clear_open_transaction; then
    log "rolled back (${reason}); previous serving again behind ${url}; leftover backup/transaction needs manual cleanup"
  else
    log "rolled back (${reason}); previous serving again behind ${url}"
  fi
  exit "$EXIT_FAILED"
}

cmd_deploy() {
  if [ "$#" -ne 6 ]; then usage; fi
  local image="$1" name="$2" port="$3" context="$4" public_ip="$5" https_port="$6"
  local previous="${name}-previous"
  local env_file="${RELEASE_DIR}/app.env"
  local tls_name="${name}-tls"
  local tls_dir="${RELEASE_DIR}/tls"
  local caddyfile="${tls_dir}/Caddyfile"
  local backup="${tls_dir}/Caddyfile.release-backup"
  local context_caddy="${context}/deploy/caddy/Caddyfile"
  local url="https://${public_ip}:${https_port}/api/health"

  check_context "$context"

  # 只清理临时构建上下文；previous 与配置备份绝不在此删除。
  # 保守失败网：基线持久化后任何未处理错误都进入实际恢复（按已持久化事务），
  # 而不是直接退出并假装无事务。恢复材料只涉本次事务文件/备份，不动用户无关容器/文件。
  # 注意：`if ! cmd` 守卫的命令失败不触发 ERR trap（POSIX 语义），所以已处理的
  # 显式 rollback_open_release 分支不受影响；只有真正未处理的错误才走此网。
  tx_err_trap() {
    local rc="$?"
    trap - ERR EXIT
    log "unexpected failure rc=${rc}; entering recovery from persisted transaction"
    if [ -f "$TRANSACTION_FILE" ] && load_transaction; then
      G_NAME="${NAME:-$G_NAME}"
      G_IMAGE="${IMAGE:-$G_IMAGE}"
      G_PREVIOUS="${PREVIOUS:-$G_PREVIOUS}"
      G_PREVIOUS_EXISTED="${PREVIOUS_EXISTED:-$G_PREVIOUS_EXISTED}"
      G_PREVIOUS_IMAGE="${PREVIOUS_IMAGE:-$G_PREVIOUS_IMAGE}"
      G_NEW_STARTED="${NEW_STARTED:-$G_NEW_STARTED}"
      G_TLS_NAME="${TLS_NAME:-$G_TLS_NAME}"
      G_TLS_EXISTED="${TLS_EXISTED:-$G_TLS_EXISTED}"
      G_CADDYFILE="${CADDYFILE:-$G_CADDYFILE}"
      G_CADDY_EXISTED="${CADDYFILE_EXISTED:-$G_CADDY_EXISTED}"
      G_BACKUP="${BACKUP:-$G_BACKUP}"
      G_BACKED_UP="${BACKED_UP:-$G_BACKED_UP}"
      G_INSTALLED_NEW="${INSTALLED_NEW:-$G_INSTALLED_NEW}"
      G_INSTALL_INTENT="${INSTALL_INTENT:-$G_INSTALL_INTENT}"
      rm -rf -- "$context"
      rollback_open_release "unexpected failure rc=${rc}"
    fi
    rm -rf -- "$context"
    log "no persisted transaction; nothing to recover (build/context stage)"
    exit "$EXIT_FAILED"
  }
  trap 'tx_err_trap' ERR
  trap 'rm -rf -- "$context"' EXIT
  # 变异前检查（读旧事务、装脚本、构建）失败直接退出：尚未动服务状态，
  # 不进恢复网；基线持久化之后才真正需要它。先暂撤，基线落盘后再启用。
  trap - ERR

  if [ -f "$TRANSACTION_FILE" ]; then
    if ! load_transaction; then
      log "cannot read open transaction; refusing new deploy"
      exit "$EXIT_FAILED"
    fi
    log "refusing new deploy: open transaction image=${IMAGE:-unknown} name=${NAME:-unknown}; finalize or rollback it first"
    exit "$EXIT_FAILED"
  fi

  install -d -m 700 "$RELEASE_DIR"
  log "installing release-transaction.sh for later finalize/rollback sessions"
  if ! install -m 700 "$context/deploy/release-transaction.sh" "$INSTALL_PATH"; then
    log "cannot install release-transaction.sh"
    exit "$EXIT_FAILED"
  fi

  # 后续失败路径共用的事务全局量。TLS/配置基线在任何变异前先捕获并持久化，
  # 使早失败（docker run/health 之前）也能按真实旧状态恢复，不误删旧 TLS。
  G_NAME="$name"
  G_IMAGE="$image"
  G_PREVIOUS="$previous"
  G_PREVIOUS_EXISTED="false"
  G_PREVIOUS_IMAGE="none"
  G_NEW_STARTED="false"
  G_TLS_NAME="$tls_name"
  if container_exists "$tls_name"; then G_TLS_EXISTED="true"; else G_TLS_EXISTED="false"; fi
  G_CADDYFILE="$caddyfile"
  if [ -f "$caddyfile" ]; then G_CADDY_EXISTED="true"; else G_CADDY_EXISTED="false"; fi
  G_BACKUP="$backup"
  G_BACKED_UP="false"
  G_INSTALLED_NEW="false"
  G_INSTALL_INTENT="false"
  G_PUBLIC_IP="$public_ip"
  G_HTTPS_PORT="$https_port"

  log "building image=${image}"
  if ! docker build --pull --tag "$image" "$context"; then
    log "build failed; serving containers untouched"
    exit "$EXIT_FAILED"
  fi

  local name_existed="false" previous_image="none"
  if container_exists "$name"; then
    name_existed="true"
    if ! previous_image="$(docker inspect --format '{{.Config.Image}}' "$name" 2>/dev/null)"; then
      previous_image="unknown"
    fi
  fi
  if [ "$name_existed" = "true" ] && container_exists "$previous"; then
    log "refusing new deploy: serving ${name} and ${previous} both present with no open transaction; finalize or rollback the prior release first (manual check needed)"
    container_state_dump "$name"
    container_state_dump "$previous"
    exit "$EXIT_FAILED"
  fi

  # 变异前先持久化基线事务：即使 parking/启动阶段被异常中断，后续 rollback
  # 也不再报“无开放事务”，而是按真实基线进入实际恢复。只记录已确认的旧状态，
  # 不删除任何用户无关容器/文件。
  G_PREVIOUS_IMAGE="$previous_image"
  if ! write_transaction "$image" "$name" "$previous" "false" "$previous_image" \
    "$tls_name" "$G_TLS_EXISTED" "$caddyfile" "$G_CADDY_EXISTED" "$backup" "false" \
    "false" "baseline" "false" "false"; then
    log "cannot persist baseline transaction; refusing to mutate serving state"
    exit "$EXIT_FAILED"
  fi
  trap 'tx_err_trap' ERR

  if [ "$name_existed" = "true" ]; then
    log "parking serving container ${name} (image=${previous_image}) as ${previous}"
    if ! docker stop "$name" >/dev/null; then
      log "unrecovered_failed_release: stop ${name} failed; serving container left stopped"
      container_state_dump "$name"
      exit "$EXIT_UNRECOVERED"
    fi
    if ! docker rename "$name" "$previous" >/dev/null; then
      log "rename ${name} to ${previous} failed; trying to start ${name} back"
      if docker start "$name" >/dev/null && wait_healthy "$name" 30; then
        log "serving container restarted; deploy aborted, previous intact"
        exit "$EXIT_FAILED"
      fi
      log "unrecovered_failed_release: ${name} stopped and cannot be renamed or restarted"
      container_state_dump "$name"
      exit "$EXIT_UNRECOVERED"
    fi
    G_PREVIOUS_EXISTED="true"
    G_PREVIOUS_IMAGE="$previous_image"
    if ! write_transaction "$image" "$name" "$previous" "true" "$previous_image" \
      "$tls_name" "$G_TLS_EXISTED" "$caddyfile" "$G_CADDY_EXISTED" "$backup" "false" \
      "false" "parked" "false" "false"; then
      log "unrecovered_failed_release: parked previous but cannot persist; manual recovery: ${previous} holds old serving image ${previous_image}"
      container_state_dump "$previous"
      exit "$EXIT_UNRECOVERED"
    fi
  fi

  local run_args=(--detach --name "$name" --restart unless-stopped --publish "${port}:8780")
  if [ -f "$env_file" ]; then
    run_args+=(--env-file "$env_file")
  fi
  log "starting new container ${name} from ${image}"
  # 已处理失败路径走显式 rollback_open_release（与 ERR 网同一恢复逻辑）。
  # docker run 本身失败时 serving 名下无本次新容器：保持 G_NEW_STARTED=false，
  # 回退绝不删除原服务；只有 run 成功后才记 new_started=true。
  if ! docker run "${run_args[@]}" "$image" >/dev/null; then
    rollback_open_release "new container failed to start"
  fi
  G_NEW_STARTED="true"
  # run 成功即落盘 new_started：随后 health/persist 任一失败的中断回退都会先比对
  # 本次新镜像再删 serving 名下容器，原服务（未停放时）不受影响。
  persist_new_started() {
    if ! write_transaction "$image" "$name" "$previous" "$G_PREVIOUS_EXISTED" "$previous_image" \
      "$tls_name" "$G_TLS_EXISTED" "$caddyfile" "$G_CADDY_EXISTED" "$backup" "$G_BACKED_UP" \
      "$G_INSTALLED_NEW" "new_started" "$G_NEW_STARTED" "$G_INSTALL_INTENT"; then
      rollback_open_release "cannot persist new_started phase"
    fi
  }
  persist_new_started
  if ! wait_healthy "$name" 30; then
    log "new container unhealthy"
    if ! docker logs "$name" 2>&1 | tail -30 >&2; then
      log "no logs from ${name}"
    fi
    rollback_open_release "new container unhealthy"
  fi
  if ! update_phase "new_healthy"; then
    rollback_open_release "cannot persist new_healthy phase"
  fi

  # TLS 收敛（带备份；previous 与备份保留到最终验收，绝不提前删除）。
  # 除基线早持久化外，这里每次变更备份/安装标记后都补写事务，使中途中断的
  # rollback 仍能还原到真实的旧 Caddy 状态，不误删或误留 TLS 配置。
  persist_tls_progress() {
    if ! write_transaction "$image" "$name" "$previous" "$G_PREVIOUS_EXISTED" "$previous_image" \
      "$tls_name" "$G_TLS_EXISTED" "$caddyfile" "$G_CADDY_EXISTED" "$backup" "$G_BACKED_UP" \
      "$G_INSTALLED_NEW" "$1" "$G_NEW_STARTED" "$G_INSTALL_INTENT"; then
      rollback_open_release "cannot persist $1 phase"
    fi
  }
  local tls_changed="false"
  if [ -f "$context_caddy" ]; then
    if [ "$G_CADDY_EXISTED" = "true" ]; then
      if ! cmp -s "$context_caddy" "$caddyfile"; then
        log "caddy config changed; backing up live config"
        if ! cp -p "$caddyfile" "$backup"; then
          rollback_open_release "cannot back up live Caddyfile"
        fi
        G_BACKED_UP="true"
        persist_tls_progress "tls_backed_up"
        if ! install -m 600 "$context_caddy" "$caddyfile"; then
          rollback_open_release "cannot install new Caddyfile"
        fi
        tls_changed="true"
      else
        log "caddy config unchanged"
      fi
    else
      # 首次安装先记意图再动文件：install 中断/部分写后 rollback 仍能按意图
      # 清除候选残留，不留无主 Caddyfile。旧备份恢复路径不受影响。
      log "installing first Caddyfile"
      G_INSTALL_INTENT="true"
      persist_tls_progress "tls_install_intent"
      if ! install -m 600 "$context_caddy" "$caddyfile"; then
        rollback_open_release "cannot install first Caddyfile"
      fi
      G_INSTALLED_NEW="true"
      persist_tls_progress "tls_installed_new"
      tls_changed="true"
    fi
  else
    log "no Caddyfile in build context; keeping live TLS config"
  fi

  if [ "$G_TLS_EXISTED" = "true" ]; then
    if [ "$tls_changed" = "true" ]; then
      log "restarting TLS container ${tls_name} for new config"
      if ! docker restart "$tls_name" >/dev/null; then
        rollback_open_release "tls restart failed"
      fi
      sleep 2
    else
      if container_running "$tls_name"; then
        log "tls container already running"
      else
        log "starting stopped TLS container ${tls_name}"
        if ! docker start "$tls_name" >/dev/null; then
          rollback_open_release "tls start failed"
        fi
        sleep 2
      fi
    fi
    if ! container_running "$tls_name"; then
      rollback_open_release "tls container not running after converge"
    fi
  else
    log "creating TLS container ${tls_name}"
    if ! docker run --detach --name "$tls_name" --restart unless-stopped --network host \
      --volume "${caddyfile}:/etc/caddy/Caddyfile:ro" \
      --volume "${name}-caddy-data:/data" \
      --volume "${name}-caddy-config:/config" \
      caddy:2 >/dev/null; then
      rollback_open_release "tls container creation failed"
    fi
    sleep 2
    if ! container_running "$tls_name"; then
      rollback_open_release "new tls container not running"
    fi
  fi
  if ! update_phase "tls_converged"; then
    rollback_open_release "cannot persist tls_converged phase"
  fi
  log "waiting for trusted HTTPS entry ${url}"
  if ! wait_https "$url" 20; then
    log "https_entry_unhealthy url=${url}"
    if ! docker logs --tail 40 "$tls_name" 2>&1 | tail -20 >&2; then
      log "no tls logs"
    fi
    rollback_open_release "https entry unhealthy"
  fi
  # deploy 自带静态验收（与 finalize/acceptance 同判据）：受信 HTTPS 之后再查
  # 首页外壳与样式/脚本字节；缺任一都实际回退，不让坏静态版本先当成功。
  if ! check_static "$public_ip" "$https_port"; then
    log "static assets failing in deploy acceptance; rolling back"
    rollback_open_release "static assets unhealthy"
  fi
  if ! update_phase "https_ok"; then
    rollback_open_release "cannot persist https_ok phase"
  fi

  trap - ERR EXIT
  if ! rm -rf -- "$context"; then
    log "cannot remove build context ${context} (continuing)"
  fi
  log "deployed_image=${image} host_port=${port} health=healthy"
  log "deployed_tls=${url} caddy_container=${tls_name}"
  log "release_transaction=open previous_retained=${previous} backup=${backup} backed_up=${G_BACKED_UP}"
  exit "$EXIT_OK"
}

cmd_finalize() {
  # 两类失败严格区分：
  # - 重验证失败（新容器缺失/不健康、HTTPS 失败）→ exit 1，事务保持开放，
  #   调用方必须 rollback（这仍是必要失败，不是收尾问题）；
  # - 清理失败（新版本健康但删 previous/备份/事务文件失败）→ exit 4，
  #   新版本已在服务，绝不自动回滚，需人工清理；previous 可能已删，
  #   日志如实报告，不再说 previous retained。
  if [ "$#" -ne 6 ]; then usage; fi
  local image="$1" name="$2" port="$3" context="$4" public_ip="$5" https_port="$6"
  check_context "$context"

  if [ ! -f "$TRANSACTION_FILE" ]; then
    log "no open release transaction; nothing to finalize (exit 4, manual check needed)"
    exit "$EXIT_FINALIZE"
  fi
  if ! load_transaction; then
    log "cannot read transaction; refusing to clean anything (exit 4, manual check needed)"
    exit "$EXIT_FINALIZE"
  fi
  if [ "${SCHEMA:-}" != "release-transaction/v1" ]; then
    log "unknown transaction schema (${SCHEMA:-missing}); refusing to clean anything (exit 4)"
    exit "$EXIT_FINALIZE"
  fi
  if [ "${NAME:-}" != "$name" ]; then
    log "transaction name mismatch (open: ${NAME:-unknown}, requested: ${name}); refusing to clean anything (exit 4)"
    exit "$EXIT_FINALIZE"
  fi
  if [ "${IMAGE:-}" != "$image" ]; then
    log "stale/mismatched finalize refused (open: ${IMAGE:-unknown}, requested: ${image}); previous retained (exit 4, manual check needed)"
    exit "$EXIT_FINALIZE"
  fi
  if ! container_exists "$name"; then
    log "serving container ${name} missing at finalize revalidation; rollback it instead (exit 1)"
    exit "$EXIT_FAILED"
  fi
  if ! wait_healthy "$name" 30; then
    log "serving container ${name} not healthy at finalize revalidation; rollback it instead (exit 1)"
    exit "$EXIT_FAILED"
  fi
  local url="https://${public_ip}:${https_port}/api/health"
  if ! wait_https "$url" 10; then
    log "https entry ${url} failing at finalize revalidation; rollback it instead (exit 1)"
    exit "$EXIT_FAILED"
  fi
  # 静态验收与 deploy 后 acceptance 一致：首页外壳与样式/脚本字节在 finalize 重验证里
  # 再查一次；缺任一都按必要失败（exit 1）走 rollback，不进 previous 清理。
  if ! check_static "$public_ip" "$https_port"; then
    log "static assets failing at finalize revalidation; rollback it instead (exit 1)"
    exit "$EXIT_FAILED"
  fi
  # 重验证已过：此时才允许清理旧版本与备份。以下任一失败都是收尾失败
  # （exit 4），不再触发回滚——回滚会销毁正健康的现行版本。
  if [ "${PREVIOUS_EXISTED:-false}" = "true" ]; then
    if container_exists "${PREVIOUS:-}"; then
      log "all acceptance passed; removing previous ${PREVIOUS}"
      if ! docker rm --force "${PREVIOUS}" >/dev/null; then
        log "finalize_cleanup_failed: new version ${image} healthy but cannot remove previous ${PREVIOUS}; manual cleanup needed (exit 4)"
        exit "$EXIT_FINALIZE"
      fi
    else
      # 事务称有 previous 却找不到：这是脏恢复点信号。finalize 仍放行新版本，
      # 但按收尾失败 exit 4 留给人工核对，不静默当清理成功。
      log "finalize_cleanup_failed: transaction records previous ${PREVIOUS:-unknown} but it is already gone before cleanup; manual check needed (exit 4)"
      exit "$EXIT_FINALIZE"
    fi
  fi
  if [ "${BACKED_UP:-false}" = "true" ] && [ -f "${BACKUP:-}" ]; then
    if ! rm -f -- "${BACKUP}"; then
      log "finalize_cleanup_failed: new version healthy but cannot remove backup ${BACKUP}; manual cleanup needed (exit 4)"
      exit "$EXIT_FINALIZE"
    fi
  fi
  if ! rm -f -- "$TRANSACTION_FILE"; then
    log "finalize_cleanup_failed: new version healthy but cannot remove transaction file; next deploy will refuse until it is cleared (exit 4)"
    exit "$EXIT_FINALIZE"
  fi
  log "release finalized: ${image} serving on port ${port}; previous cleaned"
  exit "$EXIT_OK"
}

cmd_rollback() {
  if [ "$#" -lt 6 ] || [ "$#" -gt 7 ]; then usage; fi
  local image="$1" name="$2" port="$3" context="$4" public_ip="$5" https_port="$6"
  local reason="${7:-acceptance_failed}"
  check_context "$context"

  if [ ! -f "$TRANSACTION_FILE" ]; then
    log "no open release transaction; nothing to restore (reason=${reason}); manual check needed before claiming healthy"
    exit "$EXIT_FINALIZE"
  fi
  if ! load_transaction; then
    log "cannot read transaction; leaving everything untouched (reason=${reason})"
    exit "$EXIT_FAILED"
  fi
  if [ "${SCHEMA:-}" != "release-transaction/v1" ]; then
    log "unknown transaction schema; leaving everything untouched (reason=${reason})"
    exit "$EXIT_FAILED"
  fi
  if [ "${NAME:-}" != "$name" ] || [ "${IMAGE:-}" != "$image" ]; then
    log "rollback refused: open transaction (image=${IMAGE:-unknown} name=${NAME:-unknown} phase=${PHASE:-unknown}) does not match requested (image=${image} name=${name}); leaving everything untouched"
    exit "$EXIT_FAILED"
  fi
  G_NAME="$name"
  G_IMAGE="$image"
  G_PREVIOUS="${PREVIOUS:-${name}-previous}"
  G_PREVIOUS_EXISTED="${PREVIOUS_EXISTED:-false}"
  G_PREVIOUS_IMAGE="${PREVIOUS_IMAGE:-none}"
  G_NEW_STARTED="${NEW_STARTED:-false}"
  G_TLS_NAME="${TLS_NAME:-${name}-tls}"
  G_TLS_EXISTED="${TLS_EXISTED:-false}"
  G_CADDYFILE="${CADDYFILE:-}"
  G_CADDY_EXISTED="${CADDYFILE_EXISTED:-false}"
  G_BACKUP="${BACKUP:-}"
  G_BACKED_UP="${BACKED_UP:-false}"
  G_INSTALLED_NEW="${INSTALLED_NEW:-false}"
  G_INSTALL_INTENT="${INSTALL_INTENT:-false}"
  G_PUBLIC_IP="$public_ip"
  G_HTTPS_PORT="$https_port"
  rollback_open_release "$reason"
}

main() {
  if [ "$#" -lt 1 ]; then usage; fi
  local cmd="$1"
  shift
  case "$cmd" in
    deploy) cmd_deploy "$@" ;;
    finalize) cmd_finalize "$@" ;;
    rollback) cmd_rollback "$@" ;;
    *) usage ;;
  esac
}

main "$@"
