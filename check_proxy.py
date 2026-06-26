"""Проверка прокси по требованию: жив ли и отдаёт ли RU-IP.
Запуск вручную через workflow_dispatch (воркфлоу check_proxy.yml)."""
from base import BaseSource


def main() -> None:
    res = BaseSource.check_proxy()
    if res["ok"]:
        print(f"✅ Прокси работает · IP {res['ip']} · страна {res['country']}")
        if res["error"]:
            print(f"⚠️ {res['error']}")
    else:
        print(f"❌ Прокси НЕ работает: {res['error']}")
    # в Telegram, если заданы секреты — чтобы видеть результат с телефона
    try:
        import os, requests
        tok = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat = os.environ.get("TELEGRAM_CHAT_ID")
        if tok and chat:
            mark = "✅" if res["ok"] and res["country"] == "RU" else "⚠️" if res["ok"] else "❌"
            msg = (f"{mark} Проверка прокси dacha\n"
                   f"IP: {res['ip']} · страна: {res['country']}\n"
                   f"{res['error'] or 'выход RU, всё ок'}")
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": msg}, timeout=10)
    except Exception as e:
        print(f"telegram send failed: {e}")


if __name__ == "__main__":
    main()
