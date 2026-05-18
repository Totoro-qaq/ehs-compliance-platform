# EHS Frontend

This is a dependency-free static frontend for the EHS backend.

## Local Run

Start the backend API first:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then serve the frontend from this directory:

```powershell
cd frontend
python -m http.server 5173
```

Open:

```text
http://127.0.0.1:5173
```

The default API base URL is:

```text
http://127.0.0.1:8000
```

You can change it in the browser UI. The value is stored in `localStorage`.

## Features

- API base URL setting
- Login and registration
- Password change
- Organization loading
- File upload for assessment task creation
- Task list, detail view and deletion
- EHS result, risk items and parsed text preview
