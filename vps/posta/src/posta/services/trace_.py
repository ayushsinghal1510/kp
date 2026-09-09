import json
import re
import traceback
from logging import Logger
from time import perf_counter
from typing import Any

# * Masked by key name rather than by value , so a flow key or a JWE secret cannot reach
# * the log through a field nobody thought about.
SECRET_KEY_PATTERN = re.compile(
    r'(api[-_]?key|token|password|secret|authorization|cookie|jwe|jwt)' ,
    re.IGNORECASE
)

# * Long enough to hold a whole scenario prompt and a consultation transcript , since a
# * truncated body is exactly the thing you needed to see.
MAX_VALUE_CHARS : int = 20000

def _fingerprint(text : str) -> str :
    '''
    A masked stand-in for a secret , keeping the last 4 characters as an identifier.

    # * Only for a value long enough that 4 characters are not most of it — otherwise
    # * the hint *is* the secret.
    '''

    if len(text) > 12 : return f'[redacted {len(text)} chars , ends ...{text[-4 :]}]'

    return f'[redacted {len(text)} chars]'

def redact(value : Any , depth : int = 0) -> Any :
    '''Deep copy with secrets masked and over-long strings marked with their true length.'''

    if value is None : return None

    if depth > 8 : return '[too deep]'

    if isinstance(value , dict) :

        out : dict = {}

        for key , item in value.items() :

            if SECRET_KEY_PATTERN.search(str(key)) :

                text : str = '' if item is None else str(item)
                out[str(key)] = _fingerprint(text) if text else '(empty)'

                continue

            out[str(key)] = redact(item , depth + 1)

        return out

    if isinstance(value , (list , tuple)) : return [redact(item , depth + 1) for item in value]

    if isinstance(value , str) and len(value) > MAX_VALUE_CHARS :
        return f'{value[: MAX_VALUE_CHARS]}... [+{len(value) - MAX_VALUE_CHARS} chars]'

    if isinstance(value , (int , float , bool , str)) : return value

    # * ObjectId , datetime and anything else Mongo hands back
    return str(value)

def dump(value : Any) -> str :
    '''One-line JSON , since a pretty-printed body is unreadable in a pm2 log.'''

    try : return json.dumps(redact(value) , default = str)

    # * Never raise from inside a log call and take the request down with it
    except Exception as e : return f'[unserialisable : {e}]'

class Trace :
    '''
    Per-request tracing for one call.

    # * Every line carries the same short id and a running elapsed time. posta serves
    # * several students at once , so without a correlator the log is interleaved
    # * fragments and there is no way to tell which 'assessed' belongs to which request.
    # * The step counter makes a missing step obvious : if step 4 is followed by nothing ,
    # * the handler died there.
    '''

    def __init__(self , tag : str , logger : Logger , request_id : str) :

        self.tag = tag
        self.logger = logger
        self.id = request_id

        self._started_at = perf_counter()
        self._step = 0

    def _prefix(self) -> str : return f'[{self.tag} {self.id}]'

    def elapsed_ms(self) -> int : return int((perf_counter() - self._started_at) * 1000)

    def open(self , detail : Any) -> None :
        '''The incoming request , logged before anything can reject or crash on it.'''

        self.logger.info(f'{self._prefix()} -- request {dump(detail)}')

    def log(self , message : str , detail : Any = None) -> None :

        self._step += 1

        suffix : str = '' if detail is None else f' {detail if isinstance(detail , str) else dump(detail)}'

        self.logger.info(f'{self._prefix()} {self._step}. {message}{suffix} (+{self.elapsed_ms()}ms)')

    def warn(self , message : str , detail : Any = None) -> None :
        '''Something the request survived but somebody should see.'''

        suffix : str = '' if detail is None else f' {detail if isinstance(detail , str) else dump(detail)}'

        self.logger.warning(f'{self._prefix()} ! {message}{suffix} (+{self.elapsed_ms()}ms)')

    def done(self , status : Any , payload : Any) -> None :
        '''The exact response , logged next to the request that produced it.'''

        self.logger.info(
            f'{self._prefix()} -- {status} in {self.elapsed_ms()}ms response {dump(payload)}'
        )

    def fail(self , error : Exception) -> None :
        '''Failure detail the traceback alone does not carry.'''

        self.logger.error(
            f'{self._prefix()} x FAILED after {self.elapsed_ms()}ms at step {self._step} : '
            f'{type(error).__name__} : {error} , '
            f'code = {getattr(error , "code" , None)} , '
            f'status = {getattr(error , "status_code" , None)}'
        )

        self.logger.error(traceback.format_exc())
