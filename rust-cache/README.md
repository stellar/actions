# rust-cache Action

The rust-cache action causes several folders to be cached, and sets up sccache
as a rustc wrapper so that build artifacts are cached efficiently.

Folders cached:

- `~/.cargo/registry/index/`
- `~/.cargo/registry/cache/`
- `~/.cargo/git/db/`
- `~/.cargo/target/`
- `~/.cache/sccache/`

## Usage

Add the action to any workflow before performing any `cargo` commands. This
alone is sufficient to cause the registry index to be completely cached, as well
as all build artifacts which is handled by sccache.

```yml
jobs:
  my_job:
    steps:
    - uses: stellar/actions/rust-cache@main
```

If you're `cargo install`ing binary tools in any actions, you can also add a
`--target-dir ~/.cargo/target` option to have the full set of build artifacts
cached which will speed up installing binaries that are unlikely to have changed
as a whole.
