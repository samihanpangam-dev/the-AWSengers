import asyncio

lock = asyncio.Lock()
task_finished = False

async def background_work():
    global task_finished
    async with lock:
        print("Background started, holding lock")
        await asyncio.sleep(2)
        print("Background finished, releasing lock")
        task_finished = True

async def request_handler():
    try:
        await asyncio.shield(background_work())
    except asyncio.CancelledError:
        print("Request cancelled!")
        raise

async def main():
    # Start request
    t = asyncio.create_task(request_handler())
    await asyncio.sleep(0.5)
    # Cancel request
    t.cancel()
    
    # Check if lock is still held
    print("Is lock held?", lock.locked())
    await asyncio.sleep(2)
    print("Is lock held?", lock.locked())
    print("Did task finish?", task_finished)

asyncio.run(main())
