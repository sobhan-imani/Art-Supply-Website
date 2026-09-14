import time

from django.core.management.base import BaseCommand

from orders.queue import process_jobs


class Command(BaseCommand):
    help = ("Run the queued order jobs (confirmations, notifications). "
            "Use --loop for a long running worker, or plain runs from cron.")

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true',
                            help='keep running instead of exiting when the queue is empty')
        parser.add_argument('--sleep', type=float, default=5.0,
                            help='seconds to wait between empty passes in --loop mode')
        parser.add_argument('--limit', type=int, default=None,
                            help='stop after this many jobs (per pass)')

    def handle(self, *args, **options):
        while True:
            done, failed = process_jobs(limit=options['limit'])
            if done or failed:
                self.stdout.write(f'processed {done} job(s), {failed} failed')
            if not options['loop']:
                break
            time.sleep(options['sleep'])
