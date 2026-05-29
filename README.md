# Chat App

A real-time chat application built with FastAPI, WebSockets, and PostgreSQL. This project demonstrates a professional Python web application with user authentication, peer-to-peer messaging, AI chatbot integration, and friend management features.

## Features

- 👤 **User Authentication**: Secure signup and login with password hashing
- 💬 **Real-time Chat**: WebSocket-based messaging between users
- 👥 **Friend Management**: Add friends, send friend requests, block users
- 🤖 **AI Chatbot**: Integrated AI chatbot for conversations
- 📁 **Contact Form**: Email-based contact functionality
- 🎨 **Responsive UI**: Modern template-based interface

## Tech Stack

- **Backend**: FastAPI, Uvicorn
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Real-time**: WebSockets for live messaging
- **Frontend**: Jinja2 templates, HTML/CSS/JavaScript
- **Security**: Password hashing (werkzeug), JWT-like tokens (itsdangerous)
- **AI**: OpenAI client (NVIDIA Integrate API)
- **Testing**: pytest with SQLite in-memory database

## Requirements

- Python 3.10+
- PostgreSQL 12+ (for production)
- pip or poetry

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/M4recki/Chat-app.git
cd Chat-app
```

### 2. Create and activate virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

For development and testing:

```bash
pip install -r requirements-dev.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and update values:

```bash
cp .env.example .env
```

Edit `.env` with your PostgreSQL credentials and other secrets:

```
DATABASE_URL=postgresql://user:password@localhost:5432/chatapp
SECRET_KEY=your-secret-key-here
EMAIL_RECEIVER=admin@example.com
EMAIL_PASSWORD=your-app-password
```

### 5. Create and migrate database

```bash
python project/python/models.py
```

Or using alembic (recommended for production):

```bash
alembic upgrade head
```

### 6. Run the application

```bash
cd project && python -m uvicorn python.main:app --reload
```

The application will be available at `http://localhost:8000`

## Development

### Running Tests

```bash
pytest -q
```

With coverage report:

```bash
pytest --cov=project --cov-report=html
```

### Code Quality

Format code with black:

```bash
black project/
```

Sort imports:

```bash
isort project/
```

Run linter:

```bash
flake8 project/
```

Type checking:

```bash
mypy project/python/
```

### Pre-commit Hooks

Install pre-commit hooks (auto-format and lint on git commit):

```bash
pre-commit install
```

## Project Structure

```
project/
├── python/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── routes.py            # API routes and business logic
│   ├── models.py            # SQLAlchemy ORM models
│   ├── database.py          # Database configuration
│   ├── connection_manager.py # WebSocket connection management
│   ├── chatbot_utils.py     # AI chatbot helper functions
│   ├── rate_limit.py        # In-memory rate limiter
│   ├── settings.py          # Pydantic settings & env config
│   └── setup.py             # Package setup
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── script.js
│   └── img/
└── templates/               # Jinja2 templates

tests/
├── conftest.py              # pytest configuration & fixtures
├── unit_test.py             # Unit tests
├── routes_test.py           # Route-specific integration tests
├── integration_test.py      # Integration tests
├── functional_test.py       # Functional tests
├── model_test.py            # Model tests
├── security_test.py         # Security tests
├── contract_test.py         # Contract tests
└── performance_test.py      # Performance tests
```

## Configuration

### Environment Variables

- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: Secret key for token signing (itsdangerous)
- `CHAT_SECRET_KEY`: Alternative secret for chat tokens
- `EMAIL_RECEIVER`: Email address to receive contact form submissions
- `EMAIL_PASSWORD`: App password for Gmail SMTP
- `AI_KEY`: NVIDIA Integrate API key for chatbot access
- `CHATBOT_HISTORY_LIMIT`: Number of previous chatbot exchanges included as memory context
- `TESTING`: Set to "1" during test runs (auto-set by conftest.py)

### Chatbot Configuration

Chatbot uses the NVIDIA Integrate API via the OpenAI Python client.

- Set `AI_KEY` in `.env` to your NVIDIA API key.
- Set `CHATBOT_HISTORY_LIMIT` (e.g. `8`) to control memory window size.
- The model and base URL are configured in [project/python/chatbot_utils.py](project/python/chatbot_utils.py).

## CI/CD

This project includes GitHub Actions workflows for:

- **Tests**: Automated pytest run on Python 3.10, 3.11
- **Linting**: flake8 and black formatting checks
- **Coverage**: Test coverage reporting

Workflows run on every push and pull request to `main` branch.

See `.github/workflows/python-ci.yml` for details.

## Database

### Production Setup

For production, use PostgreSQL:

```bash
pip install psycopg2-binary
```

Update `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql://user:password@localhost:5432/chatapp
```

### Testing Setup

Tests use SQLite in-memory database by default (configured in `tests/conftest.py`).

## Security

- ✅ Passwords are hashed with werkzeug PBKDF2
- ✅ Tokens are signed with itsdangerous (time-bound)
- ✅ SMTP credentials should be in `.env` (never commit)
- ✅ CORS and input validation to be added
- ⚠️ Email sending is skipped in test mode (TESTING=1)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Author

[M4recki](https://github.com/M4recki)

**Note**: This project is a portfolio/demonstration project. For production use, additional hardening, security audits, and database migrations (alembic) are recommended.
