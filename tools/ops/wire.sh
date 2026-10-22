#!/usr/bin/env bash
# Offline library workflow ported from the signed-invoice launcher.
set -euo pipefail
readonly repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
readonly base='docker.io/library/python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c'
readonly caller_uid="$(id -u)" caller_gid="$(id -g)"
print_command=false
if [[ $# -gt 0 && "$1" == --print ]]; then print_command=true; shift; fi
if [[ $# != 1 ]]; then printf '%s\n' 'Usage: bash tools/ops/wire.sh [--print] ACTION; see make help.' >&2; exit 2; fi
case "$1" in
    download|check|build|prerequisites/check|build/verify|package/build|test/package|test/repository|test/invoice|test/invoice/normative|test/invoice/adversarial|test/invoice/integration|test/voucher|lint/check|vectors/show) ;;
    *) printf '%s\n' 'Cannot run library workflow: unknown action; see make help.' >&2; exit 2 ;;
esac
readonly action=$1
if [[ "$caller_uid" == 0 || "$caller_gid" == 0 ]]; then
    printf '%s\n' 'Library workflows require a nonzero caller UID and GID.' >&2; exit 2
fi
if [[ "$repository_root" == *','* || "$repository_root" == *$'\n'* || "$repository_root" == *$'\r'* ]]; then
    printf '%s\n' 'Library workflows require a source path without commas or line breaks.' >&2; exit 2
fi
require_directory() {
    local path=$repository_root/$1
    if [[ ! -d "$path" || -L "$path" ]]; then
        printf 'Cannot use workflow input: expected a directory without a symlink: %s\n' "$1" >&2; exit 2
    fi
}
require_file() {
    local path=$repository_root/$1
    if [[ ! -f "$path" || -L "$path" ]]; then
        printf 'Cannot use workflow input: expected a regular file without a symlink: %s\n' "$1" >&2; exit 2
    fi
}
for path in .work .work/wire .work/wire/wheels .work/dist; do
    directory=$repository_root/$path
    if [[ -L "$directory" || ( -e "$directory" && ( ! -d "$directory" || "$(stat -c '%u' "$directory")" != "$caller_uid" ) ) ]]; then
        printf 'Cannot prepare library workflow: expected an owned directory without symlinks: %s\n' "$path" >&2; exit 2
    fi
done
for path in containers containers/wire requirements tools tools/ops tools/dependencies; do require_directory "$path"; done
inputs=(containers/wire/Dockerfile containers/wire/Dockerfile.dockerignore requirements/wire.lock requirements/make.json
    tools/dependencies/wheels.py tools/ops/container_guard.py)
for path in "${inputs[@]}" tools/ops/docker_client.sh tools/ops/inference_native.sh; do require_file "$path"; done
source_directories=(src tests tools containers requirements docs)
if [[ "$action" == test/repository ]]; then source_directories+=(notes); fi
case "$action" in
    package/build|test/repository|test/invoice|test/invoice/*|test/voucher|build/verify|lint/check|vectors/show)
        for path in "${source_directories[@]}"; do
            require_directory "$path"
            if [[ -n $(find "$path" -type l -print -quit) ]]; then printf 'Cannot mount symlinked source below %s.\n' "$path" >&2; exit 2; fi
        done
        for path in AGENTS.md README.md Makefile pyproject.toml MANIFEST.in ruff.toml; do require_file "$path"; done
        ;;
    test/package)
        require_file tools/ops/package.py
        require_file requirements/runtime.lock
        require_file requirements/pydantic.lock
        require_file requirements/voucher.lock
        require_directory .work/dist
        require_directory .work/wire/wheels
        ;;
esac
readonly state=$repository_root/.work/wire
common=(--init --pull never --read-only --user "$caller_uid:$caller_gid" --cap-drop ALL
    --security-opt no-new-privileges:true --cpus 2 --memory 512m --memory-swap 512m --pids-limit 64
    --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m --env PYTHONDONTWRITEBYTECODE=1
    --env IN_CONTAINER=1 --env "EXPECTED_UID=$caller_uid" --env "EXPECTED_GID=$caller_gid"
    --workdir /workspace)
wheel_mounts=(--mount "type=bind,src=$repository_root/tools/dependencies/wheels.py,dst=/workspace/tools/dependencies/wheels.py,readonly"
    --mount "type=bind,src=$repository_root/tools/ops/container_guard.py,dst=/workspace/tools/ops/container_guard.py,readonly"
    --mount "type=bind,src=$repository_root/requirements/wire.lock,dst=/input/wire.lock,readonly")
wheel_mounts+=(--mount "type=bind,src=$repository_root/requirements/make.json,dst=/input/make.json,readonly")
if [[ "$action" == download ]]; then
    bash "$repository_root/tools/ops/docker.sh" check-interface
    proxy=(bash "$repository_root/tools/ops/docker.sh")
    if "$print_command"; then proxy+=(--print); else mkdir -p -m 700 -- "$state"; fi
    exec "${proxy[@]}" run "${common[@]}" "${wheel_mounts[@]}" \
        --mount "type=bind,src=$state,dst=/output" "$base" \
        python3 -B -m tools.dependencies.wheels download --lock /input/wire.lock --make-declaration /input/make.json --output /output/wheels
fi
source "$repository_root/tools/ops/docker_client.sh"
source "$repository_root/tools/ops/inference_native.sh"
docker_client_directory=
scratch=
container_id=
publication=
caller_cancellation=0
inference_diagnostic=
inference_retirement_confirmed=true
inference_cancellation_status=0
container_id_matches_receipt() {
    [[ "$1" =~ ^[0-9a-f]{64}$ && -f "$2" && ! -L "$2" ]] && {
        cmp -s -- "$2" <(printf '%s' "$1") || cmp -s -- "$2" <(printf '%s\n' "$1")
    }
}
retire_container() {
    local status=0
    if [[ -n "$container_id" ]]; then
        if inference_native 'library container removal' 20 discard "${engine[@]}" rm --force "$container_id"; then
            container_id=
        else status=$?; fi
    fi
    return "$status"
}
cleanup() {
    local status=$? cleanup_status=0 cancelled=0
    local primary_diagnostic=$inference_diagnostic
    local native_cancellation=$inference_cancellation_status
    trap - EXIT
    trap 'cancelled=129' HUP
    trap 'cancelled=130' INT
    trap 'cancelled=143' TERM
    if "$inference_retirement_confirmed"; then
        retire_container || cleanup_status=$?
        if [[ "$status" == 0 && "$cleanup_status" != 0 ]]; then status=$cleanup_status; fi
        if "$inference_retirement_confirmed" && [[ -z "$container_id" ]]; then
            if docker_client_cleanup 2>/dev/null; then :; else
                cleanup_status=$?; if [[ "$status" == 0 ]]; then status=$cleanup_status; fi
            fi
            if [[ -n "$publication" ]]; then
                if rm -f -- "$publication" 2>/dev/null; then publication=; else
                    cleanup_status=$?; if [[ "$status" == 0 ]]; then status=$cleanup_status; fi
                fi
            fi
            if [[ "$status" == 0 && -n "$scratch" ]]; then
                if rm -rf -- "$scratch" 2>/dev/null; then scratch=; else status=$?; fi
            fi
        fi
    fi
    if [[ "$cancelled" != 0 ]]; then exit "$cancelled"; fi
    if [[ "$caller_cancellation" != 0 ]]; then exit "$caller_cancellation"; fi
    if [[ "$native_cancellation" != 0 ]]; then exit "$native_cancellation"; fi
    if "$inference_retirement_confirmed" && [[ -n "$primary_diagnostic$inference_diagnostic$scratch$container_id$docker_client_directory$publication" ]]; then
        local report_status=0
        inference_native 'workflow cleanup reporting' 10 stdio bash -eu -c '
            printf "%s" "$1" >&2
            if [[ "$2" != "$1" ]]; then printf "%s" "$2" >&2; fi
            if [[ -n "$3" ]]; then printf "Workflow evidence retained at %q.\\n" "$3" >&2; fi
            if [[ -n "$4" ]]; then printf "Cannot confirm removal of owned container %s.\\n" "$4" >&2; fi
            if [[ -n "$5" ]]; then printf "Cannot confirm removal of Docker client state %q.\\n" "$5" >&2; fi
            if [[ -n "$6" ]]; then printf "Unpublished image admission remains at %q.\\n" "$6" >&2; fi
        ' bash "$primary_diagnostic" "$inference_diagnostic" "$scratch" "$container_id" "$docker_client_directory" "$publication" || report_status=$?
        if [[ "$inference_cancellation_status" != 0 ]]; then status=$inference_cancellation_status
        elif [[ "$status" == 0 ]]; then status=$report_status; fi
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'caller_cancellation=129; exit 129' HUP
trap 'caller_cancellation=130; exit 130' INT
trap 'caller_cancellation=143; exit 143' TERM
if "$print_command"; then docker_client_prepare print
elif docker_client_prepare run; then :
else printf '%s' "$docker_client_diagnostic" >&2; exit 2; fi
cd -- "$repository_root"
run() {
    if "$print_command"; then printf '%q ' "$@"; printf '\n'; else "$@"; fi
}
native() {
    local operation=$1 budget=$2
    shift 2
    if "$print_command"; then run "$@"; else inference_native "$operation" "$budget" stdio "$@"; fi
}
managed_run() {
    if "$print_command"; then run "${engine[@]}" run --rm "$@"; return; fi
    if [[ -z "$scratch" ]]; then scratch=$(mktemp -d /tmp/wire-workflow.XXXXXXXX); fi
    rm -f -- "$scratch/run.cid" "$scratch/create.stdout"
    local create_status=0 candidate=
    inference_native 'library container creation' 30 stdio bash -eu -c '
        output=$1; shift
        umask 077; ulimit -f 4
        exec "$@" > "$output"
    ' bash "$scratch/create.stdout" "${engine[@]}" create --cidfile "$scratch/run.cid" "$@" || create_status=$?
    if ! "$inference_retirement_confirmed"; then return "$create_status"; fi
    if IFS= read -r -N 64 candidate < "$scratch/create.stdout" \
        && container_id_matches_receipt "$candidate" "$scratch/create.stdout" \
        && container_id_matches_receipt "$candidate" "$scratch/run.cid"; then container_id=$candidate; fi
    if [[ "$create_status" != 0 ]]; then return "$create_status"; fi
    if [[ -z "$container_id" ]]; then
        printf '%s\n' 'Cannot start library container: create output and CID receipt must agree exactly.' >&2; return 2
    fi
    inference_native 'library container execution' 600 stdio "${engine[@]}" start --attach "$container_id"
    retire_container
}
if [[ "$action" == prerequisites/check ]]; then
    for tool in bash make docker sha256sum stat timeout cmp cp find; do command -v "$tool" >/dev/null; done
    native 'engine prerequisite inspection' 30 "${engine[@]}" version --format '{{.Server.Version}}'
    native 'base image prerequisite inspection' 30 "${engine[@]}" image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' "$base"
    exit
fi
if [[ "$action" == check || "$action" == build ]]; then
    require_directory .work/wire/wheels
    managed_run --network none "${common[@]}" "${wheel_mounts[@]}" \
        --mount "type=bind,src=$state/wheels,dst=/dependencies,readonly" "$base" \
        python3 -B -m tools.dependencies.wheels check --lock /input/wire.lock --make-declaration /input/make.json --output /dependencies
    if [[ "$action" == check ]]; then exit; fi
    if "$print_command"; then scratch=$state/.build.PRINT; else
        if [[ -z "$scratch" ]]; then scratch=$(mktemp -d /tmp/wire-build.XXXXXXXX); fi
        mkdir -p -- "$scratch/context" "$scratch/dependencies"
        for path in "${inputs[@]}"; do
            mkdir -p -- "$scratch/context/$(dirname -- "$path")"
            cp --preserve=mode -- "$path" "$scratch/context/$path"
        done
        cp -a -- "$state/wheels/." "$scratch/dependencies/"
        managed_run --network none "${common[@]}" \
            --mount "type=bind,src=$scratch/context/tools,dst=/workspace/tools,readonly" \
            --mount "type=bind,src=$scratch/context/requirements/wire.lock,dst=/input/wire.lock,readonly" \
            --mount "type=bind,src=$scratch/context/requirements/make.json,dst=/input/make.json,readonly" \
            --mount "type=bind,src=$scratch/dependencies,dst=/dependencies,readonly" "$base" \
            python3 -B -m tools.dependencies.wheels check --lock /input/wire.lock --make-declaration /input/make.json --output /dependencies
        (cd -- "$scratch/context"; sha256sum -- "${inputs[@]}") > "$scratch/inputs"
        input_id=$(sha256sum "$scratch/inputs" | cut -d ' ' -f1)
    fi
    if "$print_command"; then input_id=PRINT; fi
    native 'offline tool image build' 600 "${engine[@]}" build --builder default --pull=false --network=none --platform linux/amd64 \
        --label "io.pay-to-play-wire.inputs=$input_id" --build-context "dependencies=$scratch/dependencies" \
        --iidfile "$scratch/image-id" -f "$scratch/context/containers/wire/Dockerfile" "$scratch/context"
    if "$print_command"; then scratch=; exit; fi
    if [[ ! -f "$scratch/image-id" || -L "$scratch/image-id" || $(stat -c '%s' "$scratch/image-id") -gt 72 ]]; then
        printf '%s\n' 'Cannot publish tool image: build returned a missing or oversized image ID record.' >&2; exit 2
    fi
    image_id=$(cat -- "$scratch/image-id")
    if [[ ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || {
        ! cmp -s -- "$scratch/image-id" <(printf '%s' "$image_id") && ! cmp -s -- "$scratch/image-id" <(printf '%s\n' "$image_id");
    }; then printf '%s\n' 'Cannot publish tool image: build returned an invalid immutable image ID.' >&2; exit 2; fi
    native 'built tool image inspection' 30 bash -eu -c '
        output=$1; shift; umask 077; ulimit -f 4; exec "$@" > "$output"
    ' bash "$scratch/observed" "${engine[@]}" image inspect --format '{{.Id}} {{index .Config.Labels "io.pay-to-play-wire.inputs"}}' "$image_id"
    if ! cmp -s -- "$scratch/observed" <(printf '%s %s\n' "$image_id" "$input_id"); then
        printf '%s\n' 'Cannot publish tool image: observed image identity or input label differs.' >&2; exit 2
    fi
    publication=$(mktemp "$state/.admission.XXXXXXXX")
    { printf '%s\n' "$image_id"; cat -- "$scratch/inputs"; } > "$publication"
    mv -T -- "$publication" "$state/admission"
    publication=
    exit
fi
record=$state/admission
if [[ ! -f "$record" || -L "$record" || $(stat -c '%s' "$record") -gt 4096 ]]; then
    printf '%s\n' 'Cannot use tool image: run make build/image to prepare its immutable admission record.' >&2; exit 2
fi
IFS= read -r image_id < "$record"
if [[ ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || ! cmp -s -- "$record" <(printf '%s\n' "$image_id"; sha256sum -- "${inputs[@]}"); then
    printf '%s\n' 'Cannot use tool image: build inputs changed or admission record is malformed; rebuild explicitly.' >&2; exit 2
fi
input_id=$(sha256sum -- "${inputs[@]}" | sha256sum | cut -d ' ' -f1)
if ! "$print_command"; then
    scratch=$(mktemp -d /tmp/image-admission.XXXXXXXX)
    native 'prepared tool image inspection' 30 bash -eu -c '
        output=$1; shift; umask 077; ulimit -f 4; exec "$@" > "$output"
    ' bash "$scratch/observed" "${engine[@]}" image inspect --format '{{.Id}} {{index .Config.Labels "io.pay-to-play-wire.inputs"}}' "$image_id"
    if ! cmp -s -- "$scratch/observed" <(printf '%s %s\n' "$image_id" "$input_id"); then
        printf '%s\n' 'Cannot use tool image: observed image identity or input label differs.' >&2; exit 2
    fi
fi
mounts=()
case "$action" in
    test/package)
        require_directory .work/dist
        mounts=(--mount "type=bind,src=$repository_root/tools/ops/package.py,dst=/workspace/tools/ops/package.py,readonly"
            --mount "type=bind,src=$repository_root/tools/dependencies/wheels.py,dst=/workspace/tools/dependencies/wheels.py,readonly"
            --mount "type=bind,src=$repository_root/tools/ops/container_guard.py,dst=/workspace/tools/ops/container_guard.py,readonly"
            --mount "type=bind,src=$repository_root/.work/dist,dst=/artifacts,readonly"
            --mount "type=bind,src=$repository_root/requirements/runtime.lock,dst=/input/runtime.lock,readonly"
            --mount "type=bind,src=$repository_root/requirements/pydantic.lock,dst=/input/pydantic.lock,readonly"
            --mount "type=bind,src=$repository_root/requirements/voucher.lock,dst=/input/voucher.lock,readonly"
            --mount "type=bind,src=$state/wheels,dst=/dependencies,readonly")
        managed_run --network none "${common[@]}" --tmpfs /runtime:rw,nosuid,nodev,exec,size=256m \
            "${mounts[@]}" "$image_id" python3 -B -m tools.ops.package check
        ;;
    *)
        for path in "${source_directories[@]}"; do
            mounts+=(--mount "type=bind,src=$repository_root/$path,dst=/workspace/$path,readonly")
        done
        for path in AGENTS.md README.md Makefile pyproject.toml MANIFEST.in ruff.toml; do
            require_file "$path"; mounts+=(--mount "type=bind,src=$repository_root/$path,dst=/workspace/$path,readonly")
        done
        case "$action" in
            package/build)
                if ! "$print_command"; then mkdir -p -m 700 -- "$repository_root/.work/dist"; fi
                mounts+=(--mount "type=bind,src=$repository_root/.work/dist,dst=/output")
                command=(python3 -B -m tools.ops.package build)
                ;;
            vectors/show) command=(python3 -B -m tools.ops.vectors) ;;
            lint/check) command=(bash -eu -c 'python3 -m ruff check --no-cache --config ruff.toml src tests tools && python3 -m ruff format --no-cache --diff --config ruff.toml src tests tools') ;;
            build/verify) command=(python3 -B -m unittest discover -s tests/repository -p test_runtime.py -v) ;;
            test/repository) command=(python3 -B -m unittest discover -s tests/repository -v) ;;
            test/invoice) command=(python3 -B -m unittest discover -s tests/invoice -v) ;;
            test/invoice/*) command=(python3 -B -m unittest discover -s "tests/invoice/${action##*/}" -v) ;;
            test/voucher) command=(python3 -B -m unittest discover -s tests/voucher -v) ;;
        esac
        managed_run --network none "${common[@]}" --env PYTHONPATH=/workspace/src "${mounts[@]}" "$image_id" "${command[@]}"
        if [[ "$action" == package/build ]] && ! "$print_command"; then
            if [[ -n $(find .work/dist ! -uid "$caller_uid" -print -quit) ]]; then printf '%s\n' 'Package output has unexpected host ownership.' >&2; exit 2; fi
        fi
        ;;
esac
