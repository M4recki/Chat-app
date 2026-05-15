# Contributing to Chat App

Thank you for your interest in contributing to Chat App! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and constructive in all interactions. We're committed to providing a welcoming and inspiring community for all.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/Chat-app.git
   cd Chat-app
   ```
3. Add upstream remote:
   ```bash
   git remote add upstream https://github.com/M4recki/Chat-app.git
   ```

## Development Setup

1. Create a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. Install development dependencies:

   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

3. Create `.env` file (copy from `.env.example`):

   ```bash
   cp .env.example .env
   ```

4. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Making Changes

### Branch Naming

Use descriptive branch names:

- `feature/description` for new features
- `bugfix/description` for bug fixes
- `docs/description` for documentation updates
- `refactor/description` for code refactoring

Example:

```bash
git checkout -b feature/add-message-reactions
```

### Coding Standards

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with these tools:

- **black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

Format your code before committing:

```bash
black project/
isort project/
```

### Commit Messages

Write clear, descriptive commit messages:

```
Add user email verification feature

- Implement email verification workflow
- Add verification token model
- Include verification templates

Closes #123
```

Format:

- First line: summary (50 characters max)
- Blank line
- Detailed description (wrapped at 72 characters)
- Reference issues: "Closes #123" or "Fixes #456"

### Testing

Write tests for new features and bug fixes:

```bash
# Run all tests
pytest -q

# Run specific test file
pytest tests/unit_test.py -v

# Run with coverage
pytest --cov=project --cov-report=html
```

Tests should:

- Be in `tests/` directory
- Follow naming convention: `test_*.py` and `def test_*():`
- Include docstrings explaining what's tested
- Use fixtures from `conftest.py`

Example test:

```python
def test_create_user(test_db_session):
    """Test creating a new user in the database."""
    user = User(name="John", email="john@example.com", ...)
    test_db_session.add(user)
    test_db_session.commit()

    assert test_db_session.query(User).filter_by(email="john@example.com").first() is not None
```

## Submitting Changes

1. Update your fork:

   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. Push to your fork:

   ```bash
   git push origin your-branch-name
   ```

3. Create a Pull Request on GitHub:
   - Reference any related issues
   - Describe your changes clearly
   - Include screenshots for UI changes

### Pull Request Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review: read through your own code
- [ ] Comments added for complex logic
- [ ] Tests written and passing (`pytest -q`)
- [ ] No breaking changes (or clearly documented)
- [ ] Updated relevant documentation
- [ ] Commit messages are clear and descriptive

## Code Review Process

- Maintainers will review your PR within a few days
- Changes may be requested - this is normal
- Once approved, your code will be merged
- Your contribution will be acknowledged

## Reporting Issues

Found a bug? Have a suggestion?

1. Check existing issues first
2. Include:
   - Clear description of the issue
   - Steps to reproduce (for bugs)
   - Expected vs actual behavior
   - Python and OS version
   - Relevant error messages or logs

## Documentation

Improvements to documentation are always welcome:

- Fix typos and grammar
- Clarify unclear sections
- Add examples
- Update outdated information

Use clear language and markdown formatting.

## Database Migrations

When modifying models:

1. Update `project/python/models.py`
2. Create migration (if using alembic):
   ```bash
   alembic revision --autogenerate -m "description"
   alembic upgrade head
   ```
3. Update tests accordingly

## Questions?

- Check existing issues/discussions
- Ask in comments on relevant issues
- Contact maintainers directly

---

Thank you for contributing! 🎉
