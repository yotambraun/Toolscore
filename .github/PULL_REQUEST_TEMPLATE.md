## Summary

<!-- What does this PR do? Why? One paragraph is enough for small changes; bullet points work for larger ones. -->

## Conventional commit title

> **This PR's title must follow the Conventional Commits spec** so that
> `python-semantic-release` can automatically derive the next version:
>
> | Prefix | Meaning | Version bump |
> |--------|---------|--------------|
> | `feat:` | New feature | **minor** (1.x.0) |
> | `fix:` | Bug fix | patch (1.0.x) |
> | `docs:` | Documentation only | no release |
> | `chore:` | Housekeeping / CI / deps | no release |
> | `refactor:` | Code restructuring, no behaviour change | no release |
> | `perf:` | Performance improvement | patch |
> | `test:` | Tests only | no release |
>
> **NEVER use `BREAKING CHANGE:` in the commit footer or `!` after the prefix**
> (e.g. `feat!:`) without explicit maintainer approval — this triggers a
> **major** version bump and a new incompatible release.

## Checklist

- [ ] Tests added or updated for the changed behaviour
- [ ] Docs updated (docstrings, `docs/`, or `TUTORIAL.md`) if the public API changed
- [ ] `ruff check toolscore` and `mypy toolscore` pass locally
- [ ] PR title follows Conventional Commits (see table above)
