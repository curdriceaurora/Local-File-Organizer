
def legacy(pool):
    buf = pool.acquire(10)
    print("buf acquired")
    pool.release(buf)
