name: land_radar scan

on:
  schedule:
    # каждые 6 часов. Actions нередко стартует с задержкой — это ок для мониторинга.
    - cron: "0 */6 * * *"
  workflow_dispatch: {}

permissions:
  contents: write          # для коммита обновлённого state/

jobs:
  scan:
    runs-on: ubuntu-latest
    concurrency:
      group: land-radar
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Run scan
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID:   ${{ secrets.TELEGRAM_CHAT_ID }}
          XAI_API_KEY:        ${{ secrets.XAI_API_KEY }}
          DACHA_DEBUG: "1"    # дамп сырого HTML в debug/; поставь "" когда селекторы устаканятся
          # Phase 2 (если появятся прокси):
          AVITO_PROXY_URL:    ${{ secrets.AVITO_PROXY_URL }}
          CIAN_PROXY_URL:     ${{ secrets.CIAN_PROXY_URL }}
        run: python scan.py

      - name: Commit state
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add state/
          [ -d debug ] && git add debug/ || true
          git diff --staged --quiet || git commit -m "state: scan $(date -u +%FT%TZ)"
          git push
