# Настройка Paddle для KikuAI Bot

## Шаг 1: Создание Product

В Paddle Dashboard (скриншот):

1. **Product name:** `KikuAI Lab API` ✅ (уже введено)

2. **Tax category:** `Standard digital goods` ✅ (правильно выбрано)

3. **Description:** Заполните описание:
   ```
   API credits for KikuAI Lab services. Top up your balance to use ReliAPI and other KikuAI products.
   ```

4. **Product icon URL:** (опционально) Можно оставить пустым

5. **Custom data:** (опционально) Можно оставить пустым

6. Нажмите **"Save"** (синяя кнопка справа вверху)

## Шаг 2: Создание Prices

После создания Product, нужно создать Prices для разных сумм:

### Для каждой суммы ($5, $10, $25, $50, $100):

1. Перейдите в **Catalog → Products → [Ваш продукт] → Prices**
2. Нажмите **"New price"**
3. Заполните:
   - **Price name:** `$5 Top-up` (или соответствующая сумма)
   - **Billing cycle:** `One-time`
   - **Price:** `$5.00` (или соответствующая сумма)
   - **Currency:** `USD`
4. Нажмите **"Save"**
5. **Скопируйте Price ID** (начинается с `pri_`)

### Создайте Prices для всех сумм:
- $5 → Price ID: `pri_5_usd` (или что-то вроде `pri_01...`)
- $10 → Price ID: `pri_10_usd`
- $25 → Price ID: `pri_25_usd`
- $50 → Price ID: `pri_50_usd`
- $100 → Price ID: `pri_100_usd`

## Шаг 3: Обновление кода

После получения Price IDs, обновите код:

1. Обновите `PRICE_TIERS` в `api/services/payment_engine.py` с реальными Price IDs
2. Измените метод `create_checkout` для использования `price_id` вместо `price_data`

## Альтернатива: Использовать price_data (текущий подход)

Если не хотите создавать Prices заранее, можно использовать `price_data`, но нужно:
1. Проверить права API ключа в Paddle Dashboard → Settings → API Keys
2. Убедиться, что ключ имеет права на создание транзакций с ad-hoc pricing

## Текущая проблема: 403 Forbidden

Ошибка 403 может быть из-за:
- API ключ не имеет прав на создание транзакций с `price_data`
- Нужно использовать `price_id` (создать Prices заранее)

## Рекомендация

**Лучше создать Prices заранее** - это более надежный подход и не требует специальных прав для ad-hoc pricing.










