NEXUS replacement
1. Replace streamlit_app.py with the included file.
2. Replace requirements.txt with the included file.
3. In Streamlit Manage app -> Settings -> Secrets add:
GROQ_API_KEY = "YOUR_NEW_GROQ_KEY"
OPENAI_API_KEY = "YOUR_OPENAI_KEY"
4. Redeploy/reboot.
IMPORTANT: revoke any API key that was previously exposed. Never put keys in GitHub code.
