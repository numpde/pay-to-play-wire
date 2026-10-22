#!/usr/bin/env bash
# GitHub orchestration stays on the host; package execution uses the frozen
# source's maintained containers. Native lifetimes follow the existing owner.
set -euo pipefail
readonly repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd -- "$repository_root"
if [[ $# != 1 || ( "$1" != publish/release && "$1" != publish/pages ) ]]; then
    printf '%s\n' 'Usage: make publish/release TAG=vX.Y.Z, or make publish/pages.' >&2; exit 2
fi
readonly action=$1
if [[ "$action" == publish/release ]]; then
    readonly tag=${PUBLISH_TAG_INPUT-}
    [[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || {
        printf '%s\n' 'Cannot publish release: supply TAG=vX.Y.Z on the Make command line.' >&2; exit 2
    }
fi
source tools/ops/inference_native.sh
inference_diagnostic=
inference_retirement_confirmed=true
inference_cancellation_status=0
scratch=
finish() {
    local status=$? report_status=0 message=$inference_diagnostic
    trap - EXIT
    if [[ -n "$scratch" ]]; then message+="Publication inputs and receipts retained at $scratch."$'\n'; fi
    if "$inference_retirement_confirmed" && [[ -n "$message" ]]; then
        inference_native 'publication reporting' 10 stdio printf '%s' "$message" || report_status=$?
        if [[ "$status" == 0 ]]; then status=$report_status; fi
    fi
    exit "$status"
}
trap finish EXIT
native() {
    local operation=$1 budget=$2 status=0
    shift 2
    inference_native "$operation" "$budget" stdio "$@" || status=$?
    if ! "$inference_retirement_confirmed"; then
        if [[ "$status" == 0 ]]; then status=2; fi
        exit "$status"
    fi
    return "$status"
}
fail() { printf '%s\n' "$1" >&2; exit 2; }
for tool in git gh curl make tar cp cmp mktemp sha256sum stat head tr grep cut; do command -v "$tool" >/dev/null; done
[[ -z $(git status --porcelain) ]] || fail 'Cannot publish: commit or remove pending checkout changes first.'
commit=$(git rev-parse HEAD)
readonly commit
if [[ -L .work || ( -e .work && ( ! -d .work || $(stat -c '%u' .work) != $(id -u) ) ) ]]; then
    fail 'Cannot retain publication evidence: .work must be an owned directory without a symlink.'
fi
mkdir -p -m 700 -- .work
scratch=$(mktemp -d "$repository_root/.work/publication.XXXXXXXX")
mapfile -t push_urls < <(git remote get-url --push --all origin)
[[ ${#push_urls[@]} == 1 ]] || fail 'Cannot publish: origin must have exactly one push URL.'
readonly push_url=${push_urls[0]}
case "$push_url" in
    git@github.com:*|https://github.com/*|ssh://git@github.com/*) ;;
    *) fail 'Cannot publish: origin must use a github.com push URL without embedded credentials.' ;;
esac
# Git resolves origin's push URL above, then resolves an explicit push URL again.
# Reject matching routing rules so the later push cannot change this destination.
routing_status=0
native 'Git URL routing inspection' 30 git config --null --get-regexp '^url\..*\.(insteadof|pushinsteadof)$' \
    > "$scratch/url-rewrites" || routing_status=$?
if [[ "$routing_status" != 0 && "$routing_status" != 1 ]]; then
    fail 'Cannot publish: Git URL routing configuration could not be inspected; retained receipts show the failure.'
fi
while IFS= read -r -d '' rule; do
    [[ "$rule" == *$'\n'* ]] || fail 'Cannot publish: Git returned malformed URL routing configuration.'
    prefix=${rule#*$'\n'}
    if [[ "$push_url" == "$prefix"* ]]; then
        fail 'Cannot publish: a Git URL rewrite matches the captured push URL; choose a canonical push URL with no matching rewrite rules.'
    fi
done < "$scratch/url-rewrites"
native 'GitHub repository inspection' 30 gh repo view "$push_url" --json nameWithOwner --jq .nameWithOwner > "$scratch/repository"
repository=$(cat "$scratch/repository")
readonly repository
[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail 'Cannot publish: GitHub returned an invalid repository identity.'
readonly repository_url=https://github.com/$repository

# Preserve the response privately and distinguish absence from authentication,
# transport and server failures. An uncertain external write is never retried.
resource_exists() {
    local endpoint=$1 response=$2 status=0
    native 'GitHub resource inspection' 30 gh api --hostname github.com --include "$endpoint" > "$response" 2> "$response.stderr" || status=$?
    if [[ "$status" == 0 ]]; then return 0; fi
    if [[ "$status" == 1 ]] && head -n 1 "$response" | tr -d '\r' | grep -Eq '^HTTP/[0-9.]+ 404( |$)'; then return 1; fi
    fail "Cannot inspect GitHub resource $endpoint (status $status); inspect the retained response before retrying."
}

if [[ "$action" == publish/release ]]; then
    readonly version=${tag#v}
    if resource_exists "repos/$repository/releases/tags/$tag" "$scratch/existing-release"; then
        fail 'Cannot publish release: this tag already has a GitHub release; inspect it instead of replacing published bytes.'
    fi
    if git show-ref --verify --quiet "refs/tags/$tag" && [[ $(git rev-parse "$tag^{}") != "$commit" ]]; then
        fail 'Cannot publish release: the existing local tag points to a different source commit.'
    fi
    mkdir -- "$scratch/source"
    native 'source archive capture' 30 git archive --format=tar --output="$scratch/source.tar" "$commit"
    tar -xf "$scratch/source.tar" -C "$scratch/source"
    mkdir -p -- "$scratch/source/.work/wire"
    cp -- .work/wire/admission "$scratch/source/.work/wire/admission"
    cp -a -- .work/wire/wheels "$scratch/source/.work/wire/wheels"
    printf 'Qualifying source %s for %s; logs: %s\n' "$commit" "$tag" "$scratch"
    native 'release package build' 660 make --no-print-directory -C "$scratch/source" package/build > "$scratch/release-build.log" 2>&1
    readonly artifacts=$scratch/source/.work/dist
    readonly wheel=wire-$version-py3-none-any.whl sdist=wire-$version.tar.gz
    [[ -f "$artifacts/$wheel" && -f "$artifacts/$sdist" ]] || fail 'Cannot publish release: TAG does not match the version in the built package.'
    native 'release qualification' 660 make --no-print-directory -C "$scratch/source" test > "$scratch/release-test.log" 2>&1
    [[ $(git rev-parse HEAD) == "$commit" && -z $(git status --porcelain) ]] || fail 'Cannot publish release: the checkout changed during qualification.'
    declare -A qualified=()
    while read -r marker digest name extra; do
        [[ "$marker" == QUALIFIED_SHA256 ]] || continue
        case "$name" in "$wheel"|"$sdist"|source.json|sha256.json) ;; *) fail 'Cannot publish release: qualification returned an unexpected artifact name.' ;; esac
        [[ -z "$extra" && "$digest" =~ ^[0-9a-f]{64}$ && ! -v qualified["$name"] ]] || fail 'Cannot publish release: qualification returned a malformed or duplicate artifact receipt.'
        qualified["$name"]=$digest
    done < "$scratch/release-test.log"
    [[ ${#qualified[@]} == 4 ]] || fail 'Cannot publish release: the installed-artifact check did not return its four exact byte identities.'
    for name in "$wheel" "$sdist" source.json sha256.json; do
        [[ $(sha256sum "$artifacts/$name" | cut -d ' ' -f1) == "${qualified[$name]}" ]] || fail 'Cannot publish release: artifact bytes changed after qualification.'
    done
    readonly wheel_hash=${qualified[$wheel]}
    readonly wheel_url=https://github.com/$repository/releases/download/$tag/$wheel
    printf 'Source: `%s`.\n\nQualified with `make package/build` and `make test` in the maintained containers.\n\n```text\nwire @ %s#sha256=%s\n```\n' \
        "$commit" "$wheel_url" "$wheel_hash" > "$scratch/release-notes.md"
    if ! git show-ref --verify --quiet "refs/tags/$tag"; then git tag -a "$tag" "$commit" -m "Release $version"; fi
    native 'release tag push' 120 git push "$push_url" "refs/tags/$tag:refs/tags/$tag"
    native 'draft release creation' 120 gh release create "$tag" --repo "$repository_url" --verify-tag --draft --title "$version" \
        --notes-file "$scratch/release-notes.md" "$artifacts/$wheel" "$artifacts/$sdist" "$artifacts/source.json" "$artifacts/sha256.json" \
        "$scratch/release-build.log" "$scratch/release-test.log"
    native 'uploaded release acquisition' 120 gh release download "$tag" --repo "$repository_url" --dir "$scratch/downloaded"
    for name in "$wheel" "$sdist" source.json sha256.json; do
        [[ $(sha256sum "$scratch/downloaded/$name" | cut -d ' ' -f1) == "${qualified[$name]}" ]] || fail 'Cannot publish release: downloaded bytes differ from the qualified artifact; the draft remains for inspection.'
    done
    for name in release-build.log release-test.log; do
        cmp -- "$scratch/$name" "$scratch/downloaded/$name" || fail 'Cannot publish release: downloaded log bytes differ; the draft remains for inspection.'
    done
    native 'verified release publication' 30 gh release edit "$tag" --repo "$repository_url" --draft=false
    printf 'Published https://github.com/%s/releases/tag/%s\n' "$repository" "$tag"
else
    [[ $(git branch --show-current) == main ]] || fail 'Cannot publish Pages: check out the main branch first.'
    native 'previous Pages source inspection' 30 git ls-remote --refs "$push_url" refs/heads/main > "$scratch/previous-main"
    previous_commit=$(cut -f1 "$scratch/previous-main")
    native 'Pages source push' 120 git push "$push_url" "$commit:refs/heads/main"
    method=POST
    if resource_exists "repos/$repository/pages" "$scratch/existing-pages"; then
        native 'Pages source configuration inspection' 30 gh api --hostname github.com "repos/$repository/pages" \
            --jq '[.source.branch, .source.path, .build_type] | join(" ")' > "$scratch/pages-source"
        if [[ $(cat "$scratch/pages-source") == 'main /docs legacy' ]]; then method=; else method=PUT; fi
    fi
    if [[ -n "$method" ]]; then
        native 'Pages source configuration' 30 gh api --hostname github.com --method "$method" "repos/$repository/pages" \
            -f 'source[branch]=main' -f 'source[path]=/docs' -f build_type=legacy > "$scratch/pages-configuration.json"
    elif [[ "$previous_commit" == "$commit" ]]; then
        # Source pushes and configuration updates already request a build.
        native 'Pages build request' 30 gh api --hostname github.com --method POST "repos/$repository/pages/builds" > "$scratch/pages-build.json"
    fi
    native 'Pages URL inspection' 30 gh api --hostname github.com "repos/$repository/pages" --jq .html_url > "$scratch/pages-url"
    readonly page_url=$(cat "$scratch/pages-url")
    [[ "$page_url" == https://* ]] || fail 'Cannot verify Pages: GitHub did not return an HTTPS site URL.'
    readonly deadline=$((SECONDS + 600))
    while (( SECONDS < deadline )); do
        native 'Pages build inspection' 30 gh api --hostname github.com "repos/$repository/pages/builds/latest" \
            --jq '.commit + " " + .status' > "$scratch/pages-status"
        read -r built_commit status < "$scratch/pages-status"
        # latest can still describe a previous failed build while a newly
        # requested build is queued, so its failure cannot decide this outcome.
        if [[ "$built_commit" == "$commit" && "$status" == built ]]; then
            native 'live Pages acquisition' 40 curl --silent --show-error --location --connect-timeout 10 --max-time 30 \
                --output "$scratch/page.html" --write-out '%{http_code}' "$page_url" > "$scratch/page-status"
            if [[ $(cat "$scratch/page-status") == 200 ]] && grep -Fq "<meta name=\"source-revision\" content=\"$commit\">" "$scratch/page.html"; then
                printf 'Published %s from %s\n' "$page_url" "$commit"
                exit
            fi
        fi
        printf 'Waiting for Pages source %s (%s %s).\n' "$commit" "$built_commit" "$status"
        sleep 5
    done
    fail 'Cannot confirm Pages publication within 600 seconds; inspect retained build and HTTP receipts before retrying.'
fi
