from enum import IntEnum


class State(IntEnum):
    CHOOSING_DOC_TYPE = 1
    ENTERING_TOPIC = 2
    ENTERING_COUNT = 3
    GENERATING = 4
