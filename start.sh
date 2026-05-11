#!/bin/bash
set -e

echo "=== Строй Финанс — запуск системы ==="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
  echo "→ Создаём виртуальное окружение..."
  python3 -m venv venv
fi

source venv/bin/activate

echo "→ Устанавливаем зависимости..."
pip install -q -r requirements.txt

echo "→ Применяем миграции..."
python manage.py migrate

echo "→ Инициализируем данные..."
python manage.py init_data

echo "→ Собираем статику..."
python manage.py collectstatic --noinput -v 0

echo ""
echo "✓ Система готова!"
echo "  Открывайте: http://127.0.0.1:8000"
echo "  Админ-панель: http://127.0.0.1:8000/admin"
echo ""

python manage.py runserver
