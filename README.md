# AIK SMS Platform

## About the Project

AIK SMS Platform is a Django-based SMS management application that integrates with the Nalo Solutions SMS API.

The application allows users to:
- Send SMS messages using Nalo Solutions.
- Select an available sender ID.
- Send messages to phone numbers.
- View SMS submission responses.
- View message history.
- Provide an endpoint for receiving delivery reports.

## Technologies Used

- Python
- Django
- PostgreSQL
- Docker
- Docker Compose
- Nalo Solutions SMS API
- Cloudflare Tunnel

## Project Setup

### Requirements

Make sure you have installed:
- Docker
- Docker Compose
- Git

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd sms_aik
```

### 2. Create your environment file

```bash
cp .env.example .env
```

Open `.env` and enter your own credentials and configuration.

Never upload your `.env` file to GitHub.

### 3. Build and start the application

```bash
docker compose up --build -d
```

### 4. Run database migrations

```bash
docker compose exec app python manage.py migrate
```

### 5. Open the application

Visit:

http://localhost:8000

## Environment Variables

| Variable | Description |
|---|---|
| DJANGO_SECRET_KEY | Django security key |
| SMS_API_KEY | Nalo API key |
| SENDER_IDS | Approved SMS sender ID |
| CALLBACK_BASE_URL | Public URL used for callbacks |
| POSTGRES_DB | PostgreSQL database name |
| POSTGRES_USER | PostgreSQL username |
| POSTGRES_PASSWORD | PostgreSQL password |
| POSTGRES_HOST | PostgreSQL host |
| POSTGRES_PORT | PostgreSQL port |
| DEBUG | Django debug setting |
| ALLOWED_HOSTS | Allowed application hostnames |

## Nalo SMS API Integration

The application uses the Nalo Solutions SMS API to submit SMS messages.

API credentials must be configured in the `.env` file.

The application uses the configured sender ID when submitting messages.

## Callback Endpoint

The callback endpoint is:

```text
/callback/
```

For local development, Nalo cannot directly access localhost. A public tunnel such as Cloudflare Tunnel is required.

Start the tunnel using:

```bash
docker compose up -d tunnel
```

Check the tunnel URL:

```bash
docker compose logs -f tunnel
```

Set the resulting public HTTPS address as `CALLBACK_BASE_URL` in `.env`.

Restart the application after changing the environment file:

```bash
docker compose up -d --force-recreate app
```

**Development note:** The callback endpoint currently responds to requests but does not yet process and save actual delivery reports. Full delivery report handling is still under development.

## Deployment

The application is intended for deployment using Render.

The production environment must use secure environment variables, a production database, and the deployed application URL as the callback base URL.

## Security

- Never commit `.env` files.
- Never expose API keys or database passwords.
- Use environment variables for sensitive configuration.
