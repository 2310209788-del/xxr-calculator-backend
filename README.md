# xxr Calculator Back End

A REST API built with the Python standard library. The server safely parses expressions and persists calculation history in SQLite.

## Runtime requirements

- Python 3.10 or later
- No third-party dependency

## Start the server

```bash
python server.py
```

The service runs at `http://127.0.0.1:8000`. It creates `xxr_calculator.db` during the first startup.

## Deployment environment variables

Cloud platforms normally provide a `PORT` environment variable. The server reads it automatically. To preserve SQLite history after service restarts, attach a persistent disk and set `DATABASE_PATH` to a file on that disk. For example, if the disk is mounted at `/var/data`, use:

```text
DATABASE_PATH=/var/data/xxr_calculator.db
```

For PythonAnywhere, use `wsgi.py` as the WSGI entry point. Its account home directory is persistent, so the default SQLite database file can remain in the project directory.

## API endpoints

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/calculate` | Calculate an expression and create a history record |
| GET | `/api/history` | Read the latest 200 history records |
| DELETE | `/api/history/{id}` | Delete one history record by ID |

## Test

```bash
python tests.py
```

The tests cover basic arithmetic, operator precedence, parentheses, unary signs, and common invalid input.

## Security note

The back end uses a recursive-descent parser for numbers, `+ - * /`, parentheses, and unary signs. It does not use `eval`, `exec`, or any technique that executes user input.
