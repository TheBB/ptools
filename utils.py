def replace_all(s, subs):
    for old, new in subs:
        s = s.replace(old, new)
    return s
