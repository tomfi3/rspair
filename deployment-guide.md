# Quick Deployment Guide

## Files to Upload to GitHub

### 1. Rename and Upload These Files:

**From this Replit:**
- `app.py` → upload as `app.py`
- `requirements-streamlit.txt` → rename to `requirements.txt` and upload
- `.streamlit/config.toml` → create folder `.streamlit` and upload this file
- `README.md` → upload as `README.md`

### 2. Quick GitHub Steps:

1. Go to github.com
2. Click "+" → "New repository"
3. Name: `uk-air-quality-dashboard`
4. Make it **Public**
5. Click "Create repository"
6. Click "uploading an existing file"
7. Drag and drop the files above

### 3. Deploy to Streamlit:

1. Go to share.streamlit.io
2. Click "Deploy an app"
3. Connect your GitHub
4. Select your new repository
5. Main file: `app.py`
6. Click "Deploy"

Your app will be live in 2-3 minutes!

## Alternative: Git Commands (if you have Git installed)

```bash
git clone https://github.com/yourusername/uk-air-quality-dashboard.git
cd uk-air-quality-dashboard
# Copy files from Replit to this folder
git add .
git commit -m "Initial commit - UK Air Quality Dashboard"
git push origin main
```