# Документация на русском

Agent Loop Guard (ALG) - локальный open-source набор инструментов для безопасной и наблюдаемой работы coding-агентов. Он обнаруживает циклы запросов, контролирует MCP-инструменты, сохраняет очищенные трассировки, сравнивает конфигурации на тестовых задачах и умеет запускать код в отдельной копии проекта через Docker.

Проект находится на стадии **`0.6.0a3`** и распространяется под Apache-2.0. Платного облака, телеметрии и закрытых функций нет.

## Быстрый старт

Пакет опубликован в PyPI под именем `agent-loop-guard-runtime`:

```bash
pipx install agent-loop-guard-runtime
alg setup
alg doctor
alg guard run
```

Откройте `http://127.0.0.1:8787` и в другом терминале выполните:

```bash
alg demo exact-loop
```

Стандартный ключ предназначен только для локального демо:

```text
alg_demo_key
```

Для реальной работы замените его через `ALG_GATEWAY_KEY` или `gateway_key` в YAML.

## Что уже работает

| Модуль | Возможности |
| --- | --- |
| Guard | циклы одинаковых запросов, tool calls, ошибок и последовательностей; Shadow/Enforce; лимиты |
| MCP Firewall | stdio и Streamable HTTP proxy; allow/deny/confirm/transform/rate limit; очередь подтверждений |
| Replay | traces, spans, события, стоимость, теги ошибок, импорт/экспорт и сравнение запусков |
| Benchmark | 30 задач, mock/HTTP/CLI adapters, deterministic scorers, paired bootstrap |
| Sandbox | приватная копия workspace, Docker limits, diff, selective apply и discard |
| VS Code | запуск runtime, Activity Bar для Guard/Replay, настройка workspace |

Sandbox является техническим preview и требует Docker. Это дополнительный слой защиты, а не сертифицированная security-система.

## Основные команды

```text
alg setup | doctor | status | open
alg guard run
alg mcp run | serve | validate-policy | test-server
alg replay import | export
alg bench dataset validate | run | compare | regression-check
alg sandbox create | exec | diff | apply | discard | export
```

## Куда идти дальше

- [Установка](../getting-started/installation.md)
- [Старт за пять минут](../getting-started/quickstart.md)
- [Подключение Codex, Claude Code, Cline и OpenCode](../getting-started/agent-setup.md)
- [Настройка YAML и переменных окружения](../getting-started/configuration.md)
- [Полный справочник CLI](../reference/cli.md)
- [Архитектура](../architecture.md)
- [Модель угроз](../security.md)
- [Текущий статус](../status.md)
- [Решение проблем](../troubleshooting.md)

Основная подробная документация пока написана на английском, чтобы проектом было проще пользоваться международному open-source сообществу. Команды и примеры одинаковы на всех страницах.

## Важные правила безопасности

1. Оставляйте сервер на `127.0.0.1`.
2. Не публикуйте provider keys, конфиги, prompts и trace exports без проверки.
3. Начинайте MCP policy с `default_action: confirm` или `deny`.
4. Оставляйте `full_content_logging: false`.
5. Перед `sandbox apply` всегда проверяйте diff и выбирайте только нужные файлы.
