#!/bin/sh
# Fetch the DAIDALUS sources at the commit from which the requirements were
# derived (a shallow fetch of that single commit). The target directory may be
# supplied as the first argument; the repository URL may be overridden using
# the DAIDALUS_URL environment variable.
set -eu

COMMIT=1c7b58e5525d5cca91cbbf4a8b7337a488243769
URL="${DAIDALUS_URL:-https://github.com/nasa/daidalus.git}"
TARGET="${1:-build/daidalus}"

if [ ! -d "$TARGET/.git" ]; then
    mkdir -p "$TARGET"
    git -C "$TARGET" init --quiet
    git -C "$TARGET" remote add origin "$URL"
fi

if [ "$(git -C "$TARGET" rev-parse --verify --quiet HEAD || true)" != "$COMMIT" ]; then
    git -C "$TARGET" fetch --quiet --depth 1 origin "$COMMIT"
    git -C "$TARGET" -c advice.detachedHead=false checkout --quiet FETCH_HEAD
fi

test "$(git -C "$TARGET" rev-parse HEAD)" = "$COMMIT"
echo "DAIDALUS $COMMIT is in $TARGET"
