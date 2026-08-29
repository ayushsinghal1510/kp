from logging import (
    Logger , getLogger , 
    StreamHandler , Formatter , 
    DEBUG , INFO , WARNING , ERROR , CRITICAL , 
    LogRecord
)

class ColoredFormatter(Formatter) : 

    def __init__(
        self , 
        fmt : str , 
        config : dict , 
        datefmt : str | None = None
    ) -> None :

        super().__init__(fmt , datefmt)
        
        self.COLORS = {
            DEBUG : config['color']['debug'] ,
            INFO : config['color']['info'] , 
            WARNING : config['color']['warning'] , 
            ERROR : config['color']['error'] , 
            CRITICAL : config['color']['critical']
        }

        self.RESET = config['color']['reset']

        self.fmt = fmt

    def format(self , record : LogRecord) -> str : 

        color = self.COLORS.get(record.levelno)

        if color : log_fmt = color + self.fmt + self.RESET
        else : log_fmt = self.fmt

        formatter = Formatter(log_fmt , self.datefmt)

        return formatter.format(record)

def load_logger(config : dict) -> Logger:

    logger: Logger = getLogger(__name__)
    logger.setLevel(DEBUG)

    if logger.handlers :

        for handler in list(logger.handlers) : logger.removeHandler(handler)

    console_handler = StreamHandler()

    log_format = config['log-format']

    formatter = ColoredFormatter(
        fmt = log_format ,
        config = config ,
        datefmt = config.get('date-format' , '')
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger

