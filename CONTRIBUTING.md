Contribution Guidelines
=======================

Great to have you here! Whether it's improving documentation, adding a new component, or reporting a bug, all contributions are welcome!

Please note that this project is released with a [Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.

- [Contribution Expectations](#contribution-expectations)
- [Contribution Process](#contribution-process)
- [After Contribution is Merged](#after-contribution-is-merged)
- [Contact Information](#contact-information)

## Contribution Expectations

#### Adding Functionality or Reporting Bugs
* Browse [open issues](https://github.com/stuntdouble/stuntdouble/issues) to find something to work on, or open a new issue to report a bug or suggest a feature.
* Bug reports should include as much detail as possible: logs, stacktraces, Python version, OS, and steps to reproduce.

#### Code Quality Expectations
- **Tests**: All new code should have corresponding unit tests (pytest)
- **Coverage**: Ensure that code coverage meets or exceeds 80%
- **Documentation**: Code should be well-documented. What code is doing should be self-explanatory based on coding conventions. Why code is doing something should be explained:
	* Python code should have docstrings (Google style)
	* `pyproject.toml` should have comments for non-obvious settings
	* Unit tests should have clear names and docstrings
	* Integration tests should document their scenarios
- **Code Style**: We follow PEP 8 conventions. Use `ruff` for formatting and linting. Run `uv run ruff check .` and `uv run ruff format --check .` to check compliance

#### Review SLAs
- Pull request reviews are targeted within 48 hours
- Maintainers will support contributors through code guidance and contribution recognition

## Contribution Process

**All contributions should be done through a fork.**

1. **Fork and Clone.** From the GitHub UI, fork the project into your user space. Then clone locally and add the upstream remote:
	```sh
	git clone git@github.com:YOUR_USERNAME/stuntdouble.git
	cd stuntdouble
	git remote add upstream git@github.com:stuntdouble/stuntdouble.git
	```

1. **Create a branch.** Use a descriptive name prefixed with `feature/` or `bugfix/` and the issue number:
	```sh
	git checkout -b feature/123-add-conditional-matching
	```

1. **Make your changes**, including documentation. Writing good commit logs is important. Follow the [Local Development](./README.md#getting-started-with-local-development) steps to get started.
	```text
	A commit log should describe what changed and why.
	Reference the GitHub issue number in the commit message (e.g., "Fixes #123").
	```

1. **Test.** Bug fixes and features **should come with tests** and coverage should meet or exceed 80%. Make sure all tests pass. Please do not submit patches that fail this check.

1. **Push your changes** to your fork's branch. Use `git rebase` (not `git merge`) to sync your work from time to time:
   ```sh
   git fetch upstream
   git rebase upstream/main
   git push origin name-of-your-branch
   ```

1. **Open a Pull Request** to the upstream repository. On your forked repo, click the "Pull Request" button and fill out the form.
1. A PR will automatically trigger CI checks against your changes.
1. Maintainers will review and may request changes or ask questions.

## After Contribution is Merged

Once the PR is approved, a maintainer will merge it and you'll be credited as a contributor. New releases are published to PyPI periodically -- check the [CHANGELOG](./CHANGELOG.md) for release notes.

## License

By contributing to StuntDouble, you agree that your contributions will be licensed under the [MIT License](./LICENSE).

## Contact Information

* Need to get in contact with the maintainers? The best people to start with are the project [code owners](https://github.com/stuntdouble/stuntdouble/blob/main/CODEOWNERS).
* Open a [GitHub Discussion](https://github.com/stuntdouble/stuntdouble/discussions) for questions or ideas.
* File a [GitHub Issue](https://github.com/stuntdouble/stuntdouble/issues) for bugs or feature requests.
