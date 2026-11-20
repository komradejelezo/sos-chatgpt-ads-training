# Soul of the System · Реклама в ChatGPT

Тизер для согласования визуального стиля. Продолжительность 19,5 секунды. Полный монтаж начинается после утверждения.

## Рендер

Нужны Python 3, Pillow, NumPy, FFmpeg с libx264, а также Open Sans и DejaVu Sans Mono. Пути к файлам шрифтов заданы в `teaser/render.py`. Распакуйте вступительный MP3 из приложенного архива и передайте путь к нему.

```sh
python -m pip install Pillow numpy
python teaser/render.py work/audio/01_Introduction.mp3 work/SOS_ChatGPT_Ads_TEASER_9x16.mp4
```

Скрипт выводит MP4 и отдельный SRT. Фразы и интервалы находятся в `teaser/captions.json`. Границы планов заданы в `CUTS`, графика каждого плана редактируется в соответствующей функции. Музыка и эффекты синтезируются при рендере. Дикторская дорожка звучит с исходной скоростью.

[Таймлайн](SCENE_TIMELINE.md) · [Проверка материалов](VERIFICATION_REPORT.md)

## Тизер V2

Оригинальный файл логотипа положите в `assets/branding/`. Рендер использует единый масштаб для обеих осей, сохраняет изображение целиком и анимирует окружающие световые элементы. Для SVG требуется CairoSVG.

```sh
python teaser/cinematic.py \
  --voice work/audio/01_Introduction.mp3 \
  --logo 'assets/branding/WhatsApp Image 2026-02-05 at 14.21.25 (2).png' \
  work/SOS_ChatGPT_Ads_TEASER_V2_CINEMATIC.mp4
```

Перспектива, параллакс и движения панелей рассчитываются в коде. Субтитры и музыка используют настройки и голос первого тизера. Для проверки расстановки сцен можно вывести отдельные кадры командой `python teaser/cinematic.py --stills work/v2-stills`.

Действия в кабинете показаны схематично по документации. [Настройка аккаунта](https://help.openai.com/en/articles/20001213-ads-manager-account-setup) · [Создание кампаний](https://help.openai.com/en/articles/20001210-creating-campaigns-for-chatgpt-ads)

## Полный ролик V3

```sh
OPENBLAS_NUM_THREADS=1 python master/render_master.py --audio work/audio
```

Зависимости и шрифты те же, что и у тизера. В `--audio` должны лежать шесть оригинальных MP3 с исходными именами. Архив исходников для передачи содержит эти дорожки отдельно от публичного GitHub.

`master/scenes.txt` задаёт действия в локальном времени каждой главы. `master/captions.json` содержит вычитанные фразы и метки. Каждая глава сохраняется в `work/v3` после успешного рендера. Повторный запуск переиспользует главы с теми же исходными данными. Итоговые MP4 и SRT создаются в `work/v3-delivery`. Для проверки отдельных планов используйте `--stills`.

Документы выпуска: [таймлайн V3](SCENE_TIMELINE_V3.md) и [отчёт V3](QUALITY_REPORT_V3.md).
