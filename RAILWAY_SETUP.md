# Railway Deployment Setup

## Files Ready to Deploy

- `kalshi_logger_cloud.py` - The logger (saves to Google Sheets)
- `requirements.txt` - Python dependencies
- `Procfile` - Tells Railway what to run
- `.gitignore` - Protects your API keys

## Step 1: Create Google Sheet + Service Account (5 min)

### A. Create a Google Sheet
1. Go to [sheets.google.com](https://sheets.google.com)
2. Create a new blank spreadsheet
3. Name it whatever you want (e.g., "Kalshi Data")
4. Copy the spreadsheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit
   ```

### B. Create Service Account
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Go to **APIs & Services > Library**
4. Search "Google Sheets API" and **Enable** it
5. Go to **APIs & Services > Credentials**
6. Click **Create Credentials > Service Account**
7. Name it anything, click through
8. Click on the service account you created
9. Go to **Keys** tab > **Add Key > Create new key > JSON**
10. Download the JSON file

### C. Share Sheet with Service Account
1. Open the JSON file you downloaded
2. Find the `client_email` field (looks like `something@project.iam.gserviceaccount.com`)
3. Go back to your Google Sheet
4. Click **Share** and paste that email
5. Give it **Editor** access

## Step 2: Push to GitHub (2 min)

```bash
cd "/Users/corbandamukaitis/Desktop/Personal Projects/15 minute trade strategy"
git init
git add .
git commit -m "Initial commit - Kalshi data logger"
git branch -M main
git remote add origin YOUR_GITHUB_REPO_URL
git push -u origin main
```

## Step 3: Deploy on Railway (3 min)

1. Go to [railway.app](https://railway.app) and log in
2. Click **New Project > Deploy from GitHub repo**
3. Select your repo
4. Go to **Variables** tab and add:
   - `GOOGLE_SHEETS_CREDS` = Paste the ENTIRE contents of your JSON key file
   - `SPREADSHEET_ID` = The ID from your Google Sheet URL
5. Railway will auto-deploy

## Step 4: Verify It's Working

1. Check Railway logs - should see "Connected to Google Sheets!"
2. Check your Google Sheet - two new tabs should appear:
   - `price_log` - Price snapshots every minute
   - `window_results` - Settlement outcomes

## That's it!

Data will accumulate 24/7 in your Google Sheet. You can view it anytime, download as CSV, or analyze directly in Sheets.

---

## Troubleshooting

**"Could not connect to Google Sheets"**
- Make sure GOOGLE_SHEETS_CREDS contains the full JSON (including curly braces)
- Make sure you enabled the Google Sheets API
- Make sure you shared the sheet with the service account email

**"Permission denied"**
- Double-check you shared the sheet with the service account email as Editor

**No data appearing**
- Check Railway logs for errors
- Markets only run during trading hours
