from string import ascii_lowercase


# https://rwmj.wordpress.com/2011/01/09/how-are-linux-drives-named-beyond-drive-26-devsdz/
def index_to_drive_name(idx: int) -> str:
    """
    Convert decimal to bijective base-26
    """

    coll = []
    d = idx + 1

    while d:
        d -= 1
        r = d % 26
        coll.append(ascii_lowercase[r])
        d //= 26

    return "".join(reversed(coll))
