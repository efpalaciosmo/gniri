#!/usr/bin/env bash
# Stage assets before changing stable. A retry may update a draft, never a release.
set -euo pipefail
tag=${1:?Release tag required}
revision=${2:?Full source revision required}
assets=${3:?Prepared release directory required}
[[ ${GITHUB_ACTIONS:-} == true && $tag =~ ^gniri-[1-9][0-9]*-[1-9][0-9]*$ ]]
[[ $revision =~ ^[a-f0-9]{40}$ && -s $assets/SHA256SUMS.bundle ]]
repository=${GITHUB_REPOSITORY:?GitHub repository required}
if existing=$(gh release view "$tag" --repo "$repository" --json isDraft,targetCommitish); then
    jq -e --arg revision "$revision" \
        '.isDraft == true and .targetCommitish == $revision' <<< "$existing" >/dev/null || {
        printf 'Refusing to overwrite a published release or a different source revision.\n' >&2
        exit 1
    }
else
    gh release create "$tag" --repo "$repository" --target "$revision" --draft \
        --title "Gniri $tag" --notes-file "$assets/release-notes.md"
fi
gh release upload "$tag" --repo "$repository" --clobber "$assets"/*
