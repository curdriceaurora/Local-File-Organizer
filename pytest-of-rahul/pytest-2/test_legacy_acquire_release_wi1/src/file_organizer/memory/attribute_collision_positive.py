
def legacy(pool, x):
    buf = pool.acquire(10)
    x.buf = 0
    pool.release(buf)
