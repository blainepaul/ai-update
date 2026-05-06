@echo off
cd /d "c:\Users\paolo\OneDrive\Desktop\My Claude\news_aggregator"
call venv\Scripts\activate.bat
python main.py >> logs\last_run.txt 2>&1
