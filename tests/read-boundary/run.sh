#!/usr/bin/env bash
# Run both READ-boundary fixtures against a compiled simulator.
set -u

test_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$test_dir/../.." && pwd)
iss_path=${1:-"$repo_root/iss"}
if [[ $# -gt 1 || ! -x "$iss_path" ]]; then
    printf 'Usage: bash %s [path-to-iss-executable]\n' "$0" >&2
    exit 2
fi

temp_dir=$(mktemp -d) || exit 2
trap 'rm -f -- "$temp_dir/stdout" "$temp_dir/stderr" "$temp_dir/trace"; rmdir -- "$temp_dir"' EXIT
failed=0
for name in valid-boundary out-boundary; do
    rm -f -- "$temp_dir/trace"
    if "$iss_path" --trace "$temp_dir/trace" "$test_dir/$name.dump" \
        < "$test_dir/$name.input" > "$temp_dir/stdout" 2> "$temp_dir/stderr"; then
        actual_status=0
    else
        actual_status=$?
    fi
    expected_status=$(cat "$test_dir/$name.expected.exit")
    ok=1
    if [[ "$actual_status" != "$expected_status" ]]; then
        printf '%s: exit %s, expected %s\n' "$name" "$actual_status" "$expected_status" >&2
        ok=0
    fi
    for stream in stdout stderr; do
        suffix=out
        [[ "$stream" == stderr ]] && suffix=stderr
        if ! cmp -s "$test_dir/$name.expected.$suffix" "$temp_dir/$stream"; then
            diff -u "$test_dir/$name.expected.$suffix" "$temp_dir/$stream" >&2
            ok=0
        fi
    done
    if [[ ! -s "$temp_dir/trace" ]]; then
        printf '%s: missing or empty trace\n' "$name" >&2
        ok=0
    else
        if grep -q '\[' "$temp_dir/trace"; then
            printf '%s: READ memory writes appeared in trace\n' "$name" >&2
            ok=0
        fi
        if [[ "$name" == valid-boundary ]]; then
            if ! awk '$2 == "df00" { found=1 } END { exit !found }' "$temp_dir/trace"; then
                printf '%s: EXIT missing from trace\n' "$name" >&2
                ok=0
            fi
        elif grep -q '^00000106 ' "$temp_dir/trace"; then
            printf '%s: faulting READ appeared in trace\n' "$name" >&2
            ok=0
        fi
    fi
    if [[ "$ok" == 1 ]]; then
        printf 'PASS %s\n' "$name"
    else
        printf 'FAIL %s\n' "$name"
        failed=1
    fi
done
exit "$failed"
