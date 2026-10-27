# Chat App

A real-time chat application built with FastAPI, WebSockets, and PostgreSQL. Features user authentication, peer-to-peer messaging, group chat, AI chatbot integration, friend management, and password reset.

## Features

- 👤 **User Authentication**: Secure signup/login with password hashing (werkzeug)
- 🔐 **Password Reset**: Forgot password flow with time-limited email links (30 min)
- 💬 **Real-time Chat**: WebSocket-based messaging between friends
- 👥 **Group Chat**: Create groups, invite members, real-time group messaging
- 👫 **Friend Management**: Send/accept/deny friend requests, block/unblock users
- 🤖 **AI Chatbot**: Integrated AI chatbot conversation (NVIDIA API via OpenAI SDK)
- 📁 **Contact Form**: Email-based contact form with SMTP
- 🎨 **Responsive UI**: Bootstrap 5 + Jinja2 templates
- ⚡ **Rate Limiting**: In-memory + Redis sliding window rate limiter

## Tech Stack

- **Backend**: FastAPI, Uvicorn / Gunicorn
- **Database**: PostgreSQL (production), SQLite (tests)
- **ORM**: SQLAlchemy 2.0 (async) + Alembic migrations
- **Real-time**: WebSockets with connection manager
- **Frontend**: Jinja2 templates, Bootstrap 5, vanilla JS
- **Security**: PBKDF2 hashing, itsdangerous signed tokens, CSRF protection
- **AI**: OpenAI Python client (NVIDIA Integrate API)
- **Testing**: pytest, pytest-cov, httpx, SQLite
- **Infra**: Docker, docker-compose, GitHub Actions CI

## Requirements

- Python 3.10+
- PostgreSQL 12+ (for production/development)
- Docker (optional, for containerized setup)

## Quick Start

### 1. Clone and setup

```bash
git clone https://github.com/M4recki/Chat-app.git
cd Chat-app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials and secrets
```

### 3. Run migrations

```bash
alembic upgrade head
```

### 4. Start the app

```bash
uvicorn project.python.main:app --reload
```

Open `http://localhost:8000`

### Docker (alternative)

```bash
docker-compose up --build
# App at http://localhost:8001, DB on port 5433
```

## Project Structure

```
├── project/
│   ├── python/
│   │   ├── main.py                 # FastAPI app factory, routes, startup
│   │   ├── settings.py             # Pydantic settings (env config)
│   │   ├── database.py             # SQLAlchemy async engine/sessions
│   │   ├── models.py               # ORM models: User, Message, Channel,
│   │   │                           #   Friend, GroupChat, GroupMember,
│   │   │                           #   GroupMessage, ChatbotMessage
│   │   ├── handlers.py             # Exception handlers (HTTP, validation)
│   │   ├── connection_manager.py   # WebSocket ConnectionManager
│   │   ├── ws.py                   # WebSocket endpoint (messaging, typing)
│   │   ├── chatbot_utils.py        # AI chatbot API integration
│   │   ├── rate_limit.py           # In-memory + Redis rate limiter
│   │   └── routes/
│   │       ├── __init__.py         # Router aggregation
│   │       ├── auth.py             # Signup, login, logout, password reset
│   │       ├── main_page.py        # Landing page
│   │       ├── profile.py          # Profile update
│   │       ├── chat.py             # 1-on-1 chat messages (HTTP)
│   │       ├── friends.py          # Friend requests, block/unblock
│   │       ├── group_chat.py       # Group chat CRUD + messaging
│   │       ├── chatbot.py          # Chatbot conversation page
│   │       ├── search.py           # User search
│   │       ├── contact.py          # Contact form
│   │       ├── online.py           # Online user status
│   │       ├── email.py            # SMTP sender, password reset token helpers
│   │       ├── helpers.py          # Auth, CSRF, channel, friendship helpers
│   │       └── template.py         # Jinja2 config, context processors
│   ├── static/
│   │   ├── css/style.css
│   │   ├── js/script.js
│   │   └── img/                    # Images (avatars, icons, decorations)
│   └── templates/                  # 20 Jinja2 HTML templates
│       ├── head.html, navbar.html, sidebar.html, footer.html
│       ├── main_page.html, login.html, sign_up.html
│       ├── forgot_password.html, reset_password.html
│       ├── friend_chat.html, single_chat.html
│       ├── group_chat.html, group_chat_list.html, create_group.html
│       ├── chatbot_chat.html, search_user.html
│       ├── friend_requests.html, update_profile.html
│       ├── contact.html, error.html
├── alembic/
│   ├── env.py, script.py.mako
│   └── versions/                   # 9 migrations
│       ├── 593b...create_initial_schema.py
│       ├── 3736...increase_password_length.py
│       ├── 347c...change_message_content_to_text.py
│       ├── c3e3...add_edited_at_to_messages.py
│       ├── 8f2e...add_last_active_to_users.py
│       ├── b5a2...add_group_chat_tables.py
│       ├── e9f7...add_user_channel_group_read_tracking.py
│       ├── b5a7...add_index_on_messages_created_at.py
│       └── 3c0b...add_indexes_on_group_chat_tables.py
├── tests/
│   ├── conftest.py                 # Fixtures and test helpers
│   ├── model_test.py               # SQLite engine/test session config
│   ├── test_routes_*.py            # Route-level HTTP tests (auth, chat, group, ...)
│   ├── test_unit_*.py              # Unit tests (helpers, email, websocket, ...)
│   ├── integration_test.py         # Integration tests
│   ├── functional_test.py          # End-to-end functional tests
│   ├── security_test.py            # Security tests (CSRF, XSS, auth)
│   ├── contract_test.py            # API contract tests
│   └── performance_test.py         # Load and rate limit tests
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── requirements.txt                # Runtime dependencies
├── requirements-dev.txt            # Dev/test dependencies
├── alembic.ini
├── pytest.ini
├── .env.example
└── README.md
```

## Testing

```bash
pytest -q                    # 310 tests
pytest --cov=project         # With coverage
pytest -k "test_login"       # Filter by name
```

## Configuration

### Environment Variables (`.env`)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/chat_app` |
| `SECRET_KEY` | Token signing key (itsdangerous) | `change-me-in-production` |
| `CHAT_SECRET_KEY` | Separate key for chat/CSRF tokens | `change-me-in-production` |
| `EMAIL_SENDER` | SMTP sender address (Gmail) | falls back to `EMAIL_RECEIVER` |
| `EMAIL_RECEIVER` | Contact form recipient | `admin@example.com` |
| `EMAIL_PASSWORD` | Gmail app password | — |
| `AI_KEY` | NVIDIA Integrate API key | — |
| `REDIS_URL` | Redis connection (for distributed rate limiting) | `""` (in-memory) |

## Security

- ✅ Passwords hashed with PBKDF2 (werkzeug)
- ✅ Auth tokens signed + timestamped (itsdangerous)
- ✅ CSRF protection on all mutation endpoints
- ✅ XSS prevention (Jinja2 auto-escape, DOM Purify)
- ✅ Rate limiting on login, search, and chatbot
- ✅ Email skipped in test mode (`TESTING=1`)
- ❗ `.env` contains secrets — never commit

## Database Migrations

```bash
alembic upgrade head         # Apply all pending
alembic downgrade -1         # Rollback one step
alembic revision --autogenerate -m "description"  # Create new
```

## License

MIT — see [LICENSE](LICENSE).

## Author

[M4recki](https://github.com/M4recki)
