from autocharging.remote import RemoteStore


def test_store_keeps_plugged_flag():
    store = RemoteStore()
    store.put("movil", 55, True)
    assert store.get_state("movil", 60) == (55, True)
    assert store.get("movil", 60) == 55
