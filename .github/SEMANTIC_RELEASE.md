# Semantic Release Guide

This project uses [python-semantic-release](https://python-semantic-release.readthedocs.io/) for automated versioning and changelog generation.

## Conventional Commits

All commits must follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Commit Types

- **feat**: A new feature (triggers minor version bump: 0.1.0 → 0.2.0)
- **fix**: A bug fix (triggers patch version bump: 0.1.0 → 0.1.1)
- **perf**: Performance improvement (triggers patch version bump)
- **docs**: Documentation changes only
- **style**: Code style changes (formatting, semicolons, etc.)
- **refactor**: Code refactoring without feature changes
- **test**: Adding or updating tests
- **build**: Changes to build system or dependencies
- **ci**: CI configuration changes
- **chore**: Other changes that don't modify src or test files

### Examples

```bash
# Feature (minor bump)
git commit -m "feat: add pytest plugin for test integration"

# Bug fix (patch bump)
git commit -m "fix: resolve Unicode encoding issues on Windows"

# Breaking change (major bump)
git commit -m "feat!: redesign metrics API

BREAKING CHANGE: metrics are now returned as dict instead of object"

# With scope
git commit -m "feat(validators): add database validator for SQL queries"

# Multiple paragraphs
git commit -m "fix: improve error messages

- Add more context to FileNotFound errors
- Include file path in error message
- Suggest common solutions"
```

## Manual Release

To create a release manually:

```bash
# 1. Ensure you're on main branch
git checkout main
git pull

# 2. Run semantic-release
pip install python-semantic-release
semantic-release version

# 3. Push changes and tags
git push
git push --tags
```

## Automated Release (GitHub Actions)

The project is configured to automatically create releases when changes are pushed to `main`:

1. Commits are analyzed for conventional commit types
2. Version is bumped according to commit types
3. CHANGELOG.md is updated automatically
4. Git tag is created
5. GitHub Release is published
6. Package is built and published to PyPI

### Required Secrets

Set these in GitHub repository settings:

- `GITHUB_TOKEN`: Automatically provided by GitHub Actions
- `PYPI_API_TOKEN`: Your PyPI API token for package publication

## Version Bumping Rules

| Commit Type | Version Change | Example |
|------------|---------------|---------|
| `feat:` | Minor (0.1.0 → 0.2.0) | New features |
| `fix:`, `perf:` | Patch (0.1.0 → 0.1.1) | Bug fixes |
| `BREAKING CHANGE:` | Major (0.1.0 → 1.0.0) | Breaking changes |
| Others | No change | Documentation, tests, etc. |

**Note**: `major_on_zero = false` means breaking changes won't bump to 1.0.0 until manually set.

## Configuration

Configuration is in `pyproject.toml`:

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
branch = "main"
upload_to_vcs_release = true
build_command = "python -m build"
major_on_zero = false
tag_format = "v{version}"
```

## Changelog

The `CHANGELOG.md` file is automatically updated with:
- Version number and date
- Categorized changes (Added, Fixed, Changed, etc.)
- Commit messages grouped by type
- Links to commits and comparisons

## Tips

1. **Use descriptive commit messages**: They appear in the changelog
2. **Group related changes**: Use multi-line commits for complex changes
3. **Test before merging**: CI runs tests before release
4. **Review changelog**: Check generated CHANGELOG.md after release
5. **Use scopes**: Help organize changelog (e.g., `feat(cli):`, `fix(metrics):`)

## Troubleshooting

### Release not triggered
- Ensure commits follow conventional format
- Check that commits are on `main` branch
- Verify GitHub Actions workflow is enabled

### Version not bumped
- Only `feat:`, `fix:`, and breaking changes trigger releases
- Other commit types (docs, style, etc.) don't bump version

### PyPI upload failed
- Check `PYPI_API_TOKEN` secret is set correctly
- Ensure version doesn't already exist on PyPI
- Verify package builds successfully locally

## Further Reading

- [Conventional Commits Specification](https://www.conventionalcommits.org/)
- [python-semantic-release Documentation](https://python-semantic-release.readthedocs.io/)
- [Semantic Versioning](https://semver.org/)
