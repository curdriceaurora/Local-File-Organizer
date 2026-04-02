import re
from typing import List
from typing import Union


def wildmatch_match(
    path_parts: List[str],
    pattern_parts: List[Union[re.Pattern, None]],
    index: int = 0,
) -> List[int]:
    if not path_parts and not pattern_parts:
        return [index]

    if not pattern_parts:
        return [index]

    if not path_parts:
        return []

    pattern_head, pattern_tail = pattern_parts[0], pattern_parts[1:]
    path_head, path_tail = path_parts[0], path_parts[1:]

    if pattern_head is not None:
        if pattern_head.fullmatch(path_head):
            return wildmatch_match(path_tail, pattern_tail, index + 1)
        else:
            return []

    consume_result = wildmatch_match(path_tail, pattern_parts, index + 1)
    no_consume_result = wildmatch_match(path_parts, pattern_tail, index)
    result = []
    if consume_result:
        result.extend(consume_result)
    if no_consume_result:
        result.extend(no_consume_result)
    return result
