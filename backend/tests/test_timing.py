"""Yanıt süresi: her yanıtta Server-Timing başlığı."""


def test_server_timing_basligi(client):
    r = client.get("/health")
    assert r.headers["server-timing"].startswith("app;dur=")
    assert float(r.headers["server-timing"].split("dur=")[1]) >= 0
    assert "server-timing" in client.get("/assets").headers  # 401 yanıtında da var
