# Chemical Expiry Monitoring System - Web Version

Flask web version of the School Laboratory Chemical Expiry and Disposal Monitoring System. This version can be hosted online and opened from any browser, including a cellphone.

## Default accounts

| Username | Password | Role |
|---|---|---|
| admin | admin123 | System Admin |
| custodian | lab123 | Laboratory Custodian |
| staff | lab123 | Laboratory Staff |
| dept | dept123 | Department Head |

## Features

- Login with roles and permissions.
- Chemical records with expiry status.
- Disposal request workflow with approval.
- Audit trail.
- CSV report downloads.
- Mobile-friendly pages so it works on a phone browser.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Host for free on Render

1. Create a free GitHub account, if you do not have one yet.
2. Create a new repository and upload all files in this folder (app.py, templates folder, static folder, requirements.txt, Procfile, render.yaml).
3. Go to render.com and sign up free.
4. Click New > Web Service.
5. Connect your GitHub repository.
6. Render auto-detects Python. Confirm:
   - Build command: pip install -r requirements.txt
   - Start command: gunicorn app:app --bind 0.0.0.0:$PORT
7. Choose the Free plan and click Create Web Service.
8. Wait for deployment. Your app gets a URL like https://your-app-name.onrender.com
9. Open that URL on your phone or any computer.

Note: free services sleep after 15 minutes of inactivity and wake on the next visit.

## Host for free on PythonAnywhere

1. Create a free account at pythonanywhere.com.
2. Upload this folder's files through the Files tab.
3. Open a Bash console and run: pip install --user -r requirements.txt
4. Go to Web tab > Add a new web app > Manual configuration > Python 3.10.
5. Set the source directory and WSGI file to point to app.py.
6. Reload the web app and open your-username.pythonanywhere.com.

## Important

Change the default passwords before real laboratory use. Set the SECRET_KEY environment variable in production.
