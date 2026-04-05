import threading
from memento.lock_manager import LocationLockManager


def test_acquire_returns_lock():
    lock = LocationLockManager.acquire("tavern")
    assert isinstance(lock, type(threading.Lock()))


def test_same_location_returns_same_lock():
    a = LocationLockManager.acquire("tavern")
    b = LocationLockManager.acquire("tavern")
    assert a is b


def test_different_locations_return_different_locks():
    a = LocationLockManager.acquire("tavern")
    b = LocationLockManager.acquire("market")
    assert a is not b


def test_concurrent_acquire_is_safe():
    results = {}
    errors = []

    def worker(loc):
        try:
            lock = LocationLockManager.acquire(loc)
            with lock:
                results[loc] = threading.current_thread().name
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(f"loc-{i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 20
