# XNU patches

`xnu/patches/` is the whole kernel: Apple's xnu-8796 (iOS 16 generation) with these patches applied in order by
`.github/workflows/xnu.yml`, which builds on GitHub's macOS runners with
[blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build) at a pinned commit.

```sh
gh workflow run xnu.yml -R YOU/ios-miatoll
gh run download RUN_ID -R YOU/ios-miatoll -n xnu-kernel -D xnu/out
```

The artifact holds `kernel.development.sweet`, which is what `tools/mkpayload.py` wants. The run also uploads
`xnu-buildtree` (the patched source plus generated headers), which `tools/xnu-cc.py` replays single compile commands
against, so a one-line fix does not cost a full CI run.

## Adding a patch

1. Fetch the build tree: `gh run download RUN_ID -n xnu-buildtree -D /tmp/bt`, then `tar xzf /tmp/bt/buildtree.tgz`.
2. Edit the source under `xnu/`, and syntax-check with `python3 tools/xnu-cc.py LOG BUILDTREE <file>`.
3. Save the diff as `xnu/patches/NNNN-sweet-<name>.patch` (next free number, applied in order).
4. Commit, push to `main`, and dispatch the workflow.

`MACOS_VERSION=13.5` selects xnu-8796, the same generation as iOS 16.6/16.7. The build runs on `macos-15`; if a future
runner's `iig` emits the wrong IORPC ABI for this xnu, pin an Xcode 15 toolchain in the workflow rather than touching
patches.
