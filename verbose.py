import logging
from datetime import datetime
from pytz import timezone, utc


LOG_LEVEL = logging.DEBUG
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"


class Verbose(object):
    """ Inherit this class to call self.logger.*** and get line number etc."""
    def __init__(self, name=None):
        self._name = name if name else self.__class__.__name__
        self._init_logging()

    def _init_logging(self):
        logging.setLoggerClass(ColoredLogger)
        self.logger = logging.getLogger(self._name)
        self.logger.propagate = False


class ColoredFormatter(logging.Formatter):
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
    COLORS = {
        'WARNING': YELLOW,
        'INFO': WHITE,
        'DEBUG': BLUE,
        'CRITICAL': YELLOW,
        'ERROR': RED
    }

    def __init__(self, msg, use_color = True):
        logging.Formatter.__init__(self, msg)
        logging.Formatter.converter = ColoredFormatter.custom_time
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in self.COLORS:
            levelname_color = COLOR_SEQ % (30 + self.COLORS[levelname]) + levelname + RESET_SEQ
            record.levelname = levelname_color
        return logging.Formatter.format(self, record)

    @staticmethod
    def custom_time(*args):
        utc_dt = utc.localize(datetime.utcnow())
        my_tz = timezone("Israel")
        converted = utc_dt.astimezone(my_tz)
        return converted.timetuple()


class ColoredLogger(logging.Logger):
    FORMAT = "[%(asctime)s] [$BOLD%(name)-15s$RESET][%(levelname)-18s] " \
             "($BOLD%(filename)s.%(funcName)s$RESET:%(lineno)d)  %(message)s"

    def __init__(self, name, use_color=True):
        logging.Logger.__init__(self, name, LOG_LEVEL)
        self.use_color = use_color
        self.COLOR_FORMAT = self.formatter_message(self.FORMAT)
        console = logging.StreamHandler()
        console.setFormatter(ColoredFormatter(self.COLOR_FORMAT))
        self.addHandler(console)
        return

    def formatter_message(self, message):
        if self.use_color:
            message = message.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
        else:
            message = message.replace("$RESET", "").replace("$BOLD", "")
        return message
