"""
Helper script to configure the Telegram bot.
Run this once locally after creating your bot via @BotFather.

Steps:
  1. Open Telegram and search for @BotFather
  2. Send /newbot and follow the instructions
  3. Copy the token BotFather gives you
  4. Run: python setup_telegram.py
  5. Send any message to your bot on Telegram when prompted
  6. The script will print the CHAT_ID to use
"""
import sys
import time
import requests


def main():
    print("=== Telegram Bot Setup ===\n")
    token = input("Incolla il token del tuo bot (da @BotFather): ").strip()
    if not token:
        print("Token vuoto. Uscita.")
        sys.exit(1)

    print("\nOra apri Telegram, cerca il tuo bot e mandagli qualsiasi messaggio.")
    input("Premi INVIO quando hai mandato il messaggio...")

    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            timeout=10,
        )
        data = resp.json()
    except Exception as exc:
        print(f"Errore nella richiesta: {exc}")
        sys.exit(1)

    if not data.get("ok"):
        print(f"Token non valido o errore: {data}")
        sys.exit(1)

    updates = data.get("result", [])
    if not updates:
        print("Nessun messaggio ricevuto. Assicurati di aver mandato un messaggio al bot e riprova.")
        sys.exit(1)

    chat_id = str(updates[-1]["message"]["chat"]["id"])
    print(f"\n✅ Chat ID trovato: {chat_id}")
    print("\nEsegui questi comandi per salvare le credenziali localmente:")
    print(f'  $env:TELEGRAM_BOT_TOKEN = "{token}"')
    print(f'  $env:TELEGRAM_CHAT_ID   = "{chat_id}"')
    print(f'\n  # Per renderle permanenti (una sola volta):')
    print(f'  [System.Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "{token}", "User")')
    print(f'  [System.Environment]::SetEnvironmentVariable("TELEGRAM_CHAT_ID",   "{chat_id}", "User")')
    print(f'\nPer GitHub Actions, aggiungi questi due Secrets nel repository:')
    print(f'  TELEGRAM_BOT_TOKEN = {token}')
    print(f'  TELEGRAM_CHAT_ID   = {chat_id}')

    # Test message
    ans = input("\nVuoi inviare un messaggio di test? (s/n): ").strip().lower()
    if ans == "s":
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "✅ AI News Aggregator configurato correttamente!"},
            timeout=10,
        )
        if r.json().get("ok"):
            print("Messaggio di test inviato con successo!")
        else:
            print(f"Errore nell'invio: {r.json()}")


if __name__ == "__main__":
    main()
