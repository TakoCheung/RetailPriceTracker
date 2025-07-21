from .celery_app import celery

@celery.task
def daily_crawl():
    # In real implementation, fetch prices from providers and store
    print("Fetching prices...")
    return "done"
