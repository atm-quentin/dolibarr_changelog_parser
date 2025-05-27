from flask_service_tools import Logger, Config

global_logger = Logger(
    name=Config.SERVICE_NAME,
    log_level=Config.LOG_LEVEL,
    log_to_file=Config.LOG_TO_FILE,
    log_file_path=Config.LOG_FILE_PATH,
    max_file_size=Config.LOG_MAX_FILE_SIZE,
    backup_count=Config.LOG_BACKUP_COUNT
).get_logger()
