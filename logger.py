import time

log_file = "log.txt"
log_fp = open(log_file, "a", encoding="utf-8")
def log(message):
    log_fp.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    log_fp.flush()
