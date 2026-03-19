WAVARCHIVE BOT — ДЕПЛОЙ НА RAILWAY

1. Зайди на railway.app → New Project → Deploy from GitHub repo
   (или просто перетащи папку с файлами)

2. После деплоя зайди в Variables и добавь:

   BOT_TOKEN     = токен от @BotFather
   ADMIN_ID      = твой Telegram ID (узнай у @userinfobot)
   GITHUB_TOKEN  = Personal Access Token
                   github.com → Settings → Developer settings
                   → Personal access tokens → Fine-grained tokens
                   → New token → выбери репо wavarchive-music
                   → Permissions: Contents = Read and Write
   GITHUB_OWNER  = artevhr
   GITHUB_REPO   = wavarchive-music
   SITE_URL      = https://artevhr.github.io/wavarchive-site/

3. Railway автоматически запустит бота.
   Логи смотри во вкладке Deployments → View Logs.

ФАЙЛЫ ДЛЯ RAILWAY:
  bot.py          — основной код
  requirements.txt — зависимости
  Procfile        — команда запуска
  railway.toml    — конфиг Railway

FLOW:
  Артист → /start → название → артист → альбом → обложка → mp3
  → тебе приходит файл + кнопки ✅ / ❌
  → ✅: mp3 загружается в GitHub, tracks.json обновляется, артист получает ссылку
  → ❌: ты пишешь причину, артист получает уведомление об отказе
