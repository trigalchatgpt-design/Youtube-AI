from __future__ import annotations
from apscheduler.schedulers.background import BackgroundScheduler
from .pipeline import generate_package

scheduler = BackgroundScheduler(timezone='America/Argentina/Buenos_Aires')

def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(lambda: generate_package('dormir'), 'cron', day_of_week='mon,wed,fri', hour=18, id='dormir-long', replace_existing=True)
    scheduler.add_job(lambda: generate_package('matematica'), 'cron', day_of_week='tue,thu', hour=18, id='matematica-long', replace_existing=True)
    scheduler.add_job(lambda: generate_package('archivo'), 'cron', day_of_week='wed,sun', hour=17, id='archivo-long', replace_existing=True)
    scheduler.start()
